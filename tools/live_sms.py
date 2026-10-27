"""Live End User Messaging SMS run (composition root, not unit-tested: it calls AWS). Usage:
  AWS_PROFILE=<p> python3 tools/live_sms.py send <case>     # one gated send from the SIMULATOR number; case = success | failure
  AWS_PROFILE=<p> python3 tools/live_sms.py settle <case>   # read the send back from CloudWatch AWS/SMSVoice, apply the decision, retry
  AWS_PROFILE=<p> python3 tools/live_sms.py optout          # STOP stand-in: list the success number, read the list back, retry
Recipients: the AWS destination simulator numbers only (messages never leave AWS; SPEC non-goal: no real phone).
Spend cap: MaxPrice per part on every call, at most MAX_SENDS sends per run, and the account's own $1 monthly SMS limit.
Log: docs/live/sms-log.jsonl (phone numbers masked, account ids masked)."""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from adapters.eum_sms import EumSmsSender, SmsOptOutList  # noqa: E402
from adapters.fakes import FixedClock, InMemoryLedger, InMemoryRegistry  # noqa: E402
from adapters.sms_metrics import CloudWatchSmsDelivery  # noqa: E402
from application.service import RecoveryService  # noqa: E402
from domain.models import Channel, OutboundRequest, Requester, UnreturnedItem  # noqa: E402

LOG, STATE = ROOT / "docs/live/sms-log.jsonl", ROOT / "docs/live/sms-state.json"
REGION = "us-east-1"
CASES = {"success": ("C-SMS-OK", "+14254147755"), "failure": ("C-SMS-FAIL", "+14254147167")}  # AWS US simulator numbers
TEXT = "Synthetic check: 3 camera kits (ledger L-{n}) were due 2026-10-15. Reply with the day and how many."
NOON = datetime(2026, 10, 27, 12, 0)  # gate clock pinned outside quiet hours, as in live_ses.py
MAX_PRICE, MAX_SENDS, CAP_USD = "0.02", 6, 1.0


def mask(s: str) -> str:
    s = re.sub(r"\d{12}", "************", str(s))
    return re.sub(r"\+(\d)(\d{3})\d{3}(\d{4})", r"+\1\2***\3", s)


def _masked(v):
    return mask(v) if isinstance(v, str) else [_masked(x) for x in v] if isinstance(v, list) else v


def _log(kind, **kw):
    row = {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "kind": kind,
           **{k: _masked(v) for k, v in kw.items()}}
    with LOG.open("a") as f:
        f.write(json.dumps(row) + "\n")
    print(json.dumps(row))


def _state():
    return json.loads(STATE.read_text()) if STATE.exists() else {"sends": {}, "count": 0}


def _session():
    import boto3
    return boto3.Session(profile_name=os.environ.get("AWS_PROFILE"))


def _origin(client) -> str:
    nums = [p for p in client.describe_phone_numbers()["PhoneNumbers"]
            if p["NumberType"] == "SIMULATOR" and p["Status"] == "ACTIVE"]
    if not nums:
        raise SystemExit("no ACTIVE SIMULATOR number; request one first (cost-check.md)")
    return nums[0]["PhoneNumberId"]


def _service(case, sender):
    cust, num = CASES[case]
    item = UnreturnedItem(f"L-{case}", cust, "Cinema camera kit", 3, date(2026, 10, 15))
    ledger = InMemoryLedger([item], {cust: {Channel.SMS: num}})
    reg = InMemoryRegistry({cust: {Channel.SMS}})
    svc = RecoveryService(ledger, reg, {Channel.SMS: sender}, FixedClock(NOON))
    return svc, reg, svc.open_recovery(item.item_id)


def _request(case):
    return OutboundRequest(Channel.SMS, CASES[case][1], TEXT.format(n=case), Requester.HUMAN)


def _guard(state):
    if state["count"] >= MAX_SENDS or state["count"] * float(MAX_PRICE) >= CAP_USD:
        _log("cap_stop", sends=state["count"], max_sends=MAX_SENDS)
        raise SystemExit(3)


def send(case):
    state = _state()
    _guard(state)
    eum = _session().client("pinpoint-sms-voice-v2", region_name=REGION)
    svc, reg, th = _service(case, EumSmsSender(eum, _origin(eum), max_price_per_part=MAX_PRICE))
    out = svc.request_send(th, _request(case))
    state["count"] += 1 if out.message_id else 0
    state["sends"][case] = {"message_id": out.message_id, "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    STATE.write_text(json.dumps(state, indent=1))
    _log("SMS_SEND", case=case, to=CASES[case][1], verdict=out.verdict.verdict.value, reason=out.verdict.reason,
         message_id=out.message_id, send_error=out.send_error, max_price_per_part=MAX_PRICE, thread=th.state.value)


def settle(case):
    state, sess = _state(), _session()
    sent = state["sends"][case]
    at = datetime.fromisoformat(sent["at"])
    cw = CloudWatchSmsDelivery(sess.client("cloudwatch", region_name=REGION))
    reading = cw.read(at, CASES[case][1], datetime.now(timezone.utc))
    _log("SMS_METRICS", case=case, sent_parts=reading.sent, delivered_parts=reading.delivered,
         window_start=reading.start.isoformat(), window_end=reading.end.isoformat(),
         event=reading.event.kind.value if reading.event else None)
    eum = sess.client("pinpoint-sms-voice-v2", region_name=REGION)
    counting = _Counting(EumSmsSender(eum, _origin(eum), max_price_per_part=MAX_PRICE))
    svc, reg, th = _service(case, counting)
    svc.request_send(th, _request(case))  # the first send, replayed in memory: no provider call is repeated here
    if reading.event is None:
        _log("SMS_DECISION", case=case, note="no metric datapoint yet; nothing decided")
        return
    d = svc.handle_event(th, reading.event, sent["message_id"])
    _log("SMS_DECISION", case=case, event=reading.event.kind.value, block_address=d.block_address,
         opt_out_customer=d.opt_out_customer, handoff=d.handoff, note=d.note, thread=th.state.value)
    _retry(case, svc, th, counting, state)


class _Counting:
    """Replays the first send without calling AWS; later sends go to the real sender (and are counted)."""
    channel = Channel.SMS

    def __init__(self, real):
        self.real, self.calls, self.replayed = real, 0, False

    def send(self, req):
        if not self.replayed:
            self.replayed = True
            return "replayed"
        self.calls += 1
        return self.real.send(req)


def _retry(case, svc, th, counting, state):
    if th.state.value == "HANDOFF":
        out = svc.request_send(th, _request(case))
        _log("SMS_RETRY", case=case, verdict=out.verdict.verdict.value, reason=out.verdict.reason,
             provider_calls=counting.calls, thread=th.state.value)
        return
    _guard(state)
    out = svc.request_send(th, _request(case))
    state["count"] += counting.calls
    STATE.write_text(json.dumps(state, indent=1))
    _log("SMS_RETRY", case=case, verdict=out.verdict.verdict.value, reason=out.verdict.reason,
         provider_calls=counting.calls, message_id=out.message_id)


def optout():
    """A simulator number cannot text STOP back, so the owner lists it the way a STOP reply would; the gate then
    learns it from the account opt-out list, not from a local flag."""
    state, sess = _state(), _session()
    eum = sess.client("pinpoint-sms-voice-v2", region_name=REGION)
    num = CASES["success"][1]
    eum.put_opted_out_number(OptOutListName="Default", OptedOutNumber=num)
    _log("SMS_OPTOUT_LISTED", number=num, list="Default", by="owner, standing in for a STOP reply")
    events = SmsOptOutList(eum, "Default").poll([num], datetime.now(timezone.utc))
    _log("SMS_OPTOUT_READ", numbers=[e.address for e in events], kinds=[e.kind.value for e in events])
    counting = _Counting(EumSmsSender(eum, _origin(eum), max_price_per_part=MAX_PRICE))
    svc, reg, th = _service("success", counting)
    before = svc.request_send(th, _request("success"))  # replay of the delivered send (no AWS call)
    for ev in events:
        d = svc.handle_event(th, ev)
        _log("SMS_DECISION", case="optout", event=ev.kind.value, opt_out_customer=d.opt_out_customer,
             handoff=d.handoff, note=d.note, thread=th.state.value)
    after = svc.request_send(th, _request("success"))
    _log("SMS_RETRY", case="optout", before=before.verdict.verdict.value, verdict=after.verdict.verdict.value,
         reason=after.verdict.reason, provider_calls=counting.calls, thread=th.state.value)


if __name__ == "__main__":
    cmd = sys.argv[1]
    {"send": lambda: send(sys.argv[2]), "settle": lambda: settle(sys.argv[2]), "optout": optout}[cmd]()
