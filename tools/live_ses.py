"""Live SES run (composition root, not unit-tested: it calls AWS). Usage:
  AWS_PROFILE=<p> python3 tools/live_ses.py send     # 4 gated sends via the real service + SesEmailSender
  AWS_PROFILE=<p> python3 tools/live_ses.py settle   # read CloudWatch events, apply decisions, retry sends
  python3 tools/live_ses.py reply "<text>"           # feed a reply read from the test inbox into the reading step
Recipients: the owner's own inbox and the SES mailbox simulator only (SPEC non-goal). Log: docs/live/live-log.jsonl."""
from __future__ import annotations

import json
import os
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from adapters.fakes import FixedClock, InMemoryLedger, InMemoryRegistry  # noqa: E402
from adapters.ses import SesEmailSender  # noqa: E402
from adapters.ses_metrics import CloudWatchSesEvents  # noqa: E402
from application.service import RecoveryService  # noqa: E402
from domain.models import Channel, OutboundRequest, Requester, UnreturnedItem  # noqa: E402
from infrastructure.aws_clients import make_client  # noqa: E402

LOG, STATE = ROOT / "docs/live/live-log.jsonl", ROOT / "docs/live/state.json"
REGION, CONFIG_SET = "us-east-1", "cds-rr"
SOURCE = os.environ.get("CDS_SENDER", "")  # your SES-verified address; never committed
CASES = {  # case tag -> (customer, recipient). Synthetic customers; recipients are owner/simulator only.
    "self": ("C-S", SOURCE),  # owner inbox = the verified sender itself
    "success": ("C-OK", "success@simulator.amazonses.com"),
    "bounce": ("C-BN", "bounce@simulator.amazonses.com"),
    "complaint": ("C-CP", "complaint@simulator.amazonses.com"),
}
TEXT = "Synthetic check: 3 camera kits (ledger L-{n}) were due 2026-10-15. Which day will you return them, and how many?"
NOON = datetime(2026, 10, 26, 12, 0)  # gate clock pinned outside quiet hours (real local time 05:xx would HOLD)


def _log(kind, **kw):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a") as f:
        f.write(json.dumps({"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "kind": kind, **kw}) + "\n")


def _service(sender):
    items = [UnreturnedItem(f"L-{k}", c, "Cinema camera kit", 3, date(2026, 10, 15)) for k, (c, _) in CASES.items()]
    ledger = InMemoryLedger(items, {c: {Channel.EMAIL: a} for c, a in CASES.values()})
    reg = InMemoryRegistry({c: {Channel.EMAIL} for c, _ in CASES.values()})
    return RecoveryService(ledger, reg, {Channel.EMAIL: sender}, FixedClock(NOON)), reg


def _sender(tag):
    import boto3
    sess = boto3.Session(profile_name=os.environ.get("AWS_PROFILE"))
    return SesEmailSender(sess.client("ses", region_name=REGION), SOURCE, CONFIG_SET, {"case": tag}), sess


def send():
    state = {"sent_at": datetime.now(timezone.utc).isoformat(), "ids": {}}
    for tag, (cust, addr) in CASES.items():
        sender, _ = _sender(tag)
        svc, _reg = _service(sender)
        th = svc.open_recovery(f"L-{tag}")
        out = svc.request_send(th, OutboundRequest(Channel.EMAIL, addr, TEXT.format(n=tag), Requester.HUMAN))
        state["ids"][tag] = out.message_id
        _log("SEND", case=tag, to=addr, verdict=out.verdict.verdict.value, reason=out.verdict.reason, message_id=out.message_id)
    STATE.write_text(json.dumps(state))


def settle():
    state = json.loads(STATE.read_text())
    cw = CloudWatchSesEvents(None, "case")
    for tag, (cust, addr) in CASES.items():
        sender, sess = _sender(tag)
        cw._client = sess.client("cloudwatch", region_name=REGION)
        svc, reg = _service(sender)
        th = svc.open_recovery(f"L-{tag}")
        events = cw.poll(tag, addr, datetime.now())
        _log("EVENTS", case=tag, kinds=[e.kind.value for e in events])
        for ev in events:
            d = svc.handle_event(th, ev, state["ids"][tag])
            _log("DECISION", case=tag, event=ev.kind.value, block_address=d.block_address,
                 opt_out_customer=d.opt_out_customer, handoff=d.handoff, note=d.note)
        retry = svc.request_send(th, OutboundRequest(Channel.EMAIL, addr, TEXT.format(n=tag), Requester.HUMAN))
        _log("RETRY_SEND", case=tag, verdict=retry.verdict.verdict.value, reason=retry.verdict.reason,
             ses_called=retry.message_id is not None)
        if retry.message_id is None:
            continue  # nothing more to say; a PASS retry would have called SES again


def reply(text):
    svc, _ = _service(None)
    th = svc.open_recovery("L-self")
    th.mark_sent()  # the outbound already went out in `send`; the replay thread is rebuilt in memory
    res = svc.handle_reply(th, text)
    _log("REPLY_READ", text=text, quantity=res.reading.quantity, date=str(res.reading.return_date),
         confidence=res.reading.confidence, matches=res.comparison.matches, reason=res.comparison.reason)
    if res.proposed_posting:
        svc.confirm_posting(th, res)
        _log("POSTED", item="L-self", state=th.state.value)


if __name__ == "__main__":
    {"send": send, "settle": settle}.get(sys.argv[1], lambda: reply(sys.argv[2]))()
