"""Live Bedrock run for the reply-reading assist (composition root, not unit-tested: it calls AWS). Usage:
  AWS_PROFILE=<p> python3 tools/live_bedrock.py [model_id]     # default amazon.nova-micro-v1:0, us-east-1
Three synthetic low-confidence replies go through RecoveryService.handle_reply with BedrockReplyAssistant.
Senders are in-memory fakes: a follow-up the model drafts gets a real gate verdict but is never delivered.
Log: docs/live/bedrock-log.jsonl (tokens, estimated cost, gate verdicts; account ids masked). Spend cap: $1 total."""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from adapters.bedrock import BedrockReplyAssistant  # noqa: E402
from adapters.fakes import FakeSender, FixedClock, InMemoryLedger, InMemoryRegistry  # noqa: E402
from application.service import RecoveryService  # noqa: E402
from domain.models import Channel, OutboundRequest, Requester, UnreturnedItem  # noqa: E402
from infrastructure.aws_clients import make_client  # noqa: E402

LOG = ROOT / "docs/live/bedrock-log.jsonl"
REGION = os.environ.get("CDS_BEDROCK_REGION", "us-east-1")
NOON = datetime(2026, 10, 26, 12, 0)  # gate clock pinned outside quiet hours
# Amazon Nova Micro on-demand list price (USD per 1,000 tokens), used only for the spend cap estimate.
PRICE_IN, PRICE_OUT, CAP_USD = 0.000035, 0.00014, 1.0
REPLIES = [  # synthetic; each one is below the regex reader's confidence threshold
    "the three cameras will be back on saturday morning",
    "We'll drop all of them off friday, sorry for the delay",
    "sorry, been travelling, will sort it out soon",
]


def _mask(s: str) -> str:
    return re.sub(r"user/[\w+=,.@-]+", "user/<iam-user>", re.sub(r"\d{12}", "************", s))


def _log(kind, **kw):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a") as f:
        f.write(json.dumps({"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "kind": kind, **kw}) + "\n")


def main(model_id: str) -> int:
    assistant = BedrockReplyAssistant(make_client("bedrock", REGION), model_id)
    spent, ok = 0.0, 0
    for n, text in enumerate(REPLIES, 1):
        item = UnreturnedItem(f"L-B{n}", f"C-B{n}", "camera kit", 3, date(2026, 10, 15))
        ledger = InMemoryLedger([item], {item.customer_id: {Channel.EMAIL: f"c{n}@example.test"}})
        reg = InMemoryRegistry({item.customer_id: {Channel.EMAIL}})
        email = FakeSender(Channel.EMAIL)
        svc = RecoveryService(ledger, reg, {Channel.EMAIL: email}, FixedClock(NOON), assistant=assistant)
        thread = svc.open_recovery(item.item_id)
        svc.request_send(thread, OutboundRequest(Channel.EMAIL, f"c{n}@example.test", "Return check.", Requester.HUMAN))
        assistant.last_usage = None
        res = svc.handle_reply(thread, text)
        usage = assistant.last_usage or {}
        cost = usage.get("inputTokens", 0) / 1000 * PRICE_IN + usage.get("outputTokens", 0) / 1000 * PRICE_OUT
        spent += cost
        entries = [{k: (_mask(v) if isinstance(v, str) else v) for k, v in e.items()} for e in reg.entries()
                   if e["kind"] in ("ASSIST", "ASSIST_FAILED", "READ") or e.get("by") == "AGENT"]
        ok += 1 if usage else 0
        _log("bedrock_reply", model=model_id, region=REGION, reply=text, usage=usage, est_usd=round(cost, 7),
             source=res.reading.source, qty=res.reading.quantity, date=str(res.reading.return_date),
             confidence=res.reading.confidence, match=res.comparison.matches, state=thread.state.value,
             follow_up_verdict=res.follow_up.verdict.verdict.value if res.follow_up else None,
             follow_up_text=email.calls[-1].text if res.follow_up and len(email.calls) > 1 else None,
             registry=entries)
        if spent > CAP_USD:
            _log("cap_stop", spent_usd=spent)
            break
    _log("bedrock_run_summary", model=model_id, calls_with_usage=ok, attempted=len(REPLIES), est_usd=round(spent, 7))
    print(f"calls with usage {ok}/{len(REPLIES)}, estimated ${spent:.6f}")
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "amazon.nova-micro-v1:0"))
