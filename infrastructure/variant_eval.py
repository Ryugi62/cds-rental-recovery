"""k-variant reply repetition on the real RecoveryService with fakes (synthetic data only).
closed = reply matched the ledger and posted; handoff = no auto posting, a human gets the item.
policy violation = auto-closed although the expected outcome is hand-off (wrong qty/low confidence), or any send after opt-out."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import List

from adapters.fakes import FakeSender, FixedClock, InMemoryLedger, InMemoryRegistry
from application.service import RecoveryService
from domain.models import (Channel, DeliveryEvent, EventKind, OutboundRequest, Requester, UnreturnedItem)

NOW = datetime(2026, 10, 26, 12, 0)  # a Monday, outside quiet hours
ITEM = UnreturnedItem("L-104", "C-104", "Cinema camera kit", 3, date(2026, 10, 15))
ADDR = "customer@example.test"


@dataclass(frozen=True)
class Variant:
    variant_id: str
    text: str
    expect: str  # CLOSED | HANDOFF  (author's label, written before running)


VARIANTS: List[Variant] = [
    Variant("plain-en", "I'll bring back 3 on Thursday", "CLOSED"),
    Variant("polite-en", "Sorry for the delay. I'll bring back 3 on Thursday.", "CLOSED"),
    Variant("ko", "목요일에 3개 반납할게요", "CLOSED"),
    Variant("ko-short", "내일 3대 가져다 드릴게요", "CLOSED"),
    Variant("iso-date", "Returning 3 units on 2026-10-30", "CLOSED"),
    Variant("units-word", "Tomorrow, 3 cameras", "CLOSED"),
    Variant("weekday-abbr", "Fri, 3 pcs", "CLOSED"),
    Variant("with-signature", "Will return 3 on Friday.\n--\nSent from my phone", "CLOSED"),
    Variant("qty-mismatch", "I'll bring back 2 on Thursday", "HANDOFF"),
    Variant("no-number", "I'll return them soon", "HANDOFF"),
    Variant("already-returned", "I already returned everything last week", "HANDOFF"),
    Variant("stop-request", "Please stop emailing me", "HANDOFF"),
    Variant("noise-number", "Order #4471: back on Thursday", "HANDOFF"),
    Variant("empty", "", "HANDOFF"),
]


@dataclass(frozen=True)
class Row:
    variant_id: str
    expect: str
    final_state: str
    handoff_turn: int  # 0 = no hand-off; 1 = at the first reply
    violation: bool


@dataclass(frozen=True)
class Report:
    rows: List[Row]
    k: int
    closed: int
    handoff: int
    closed_rate: float
    closed_expected: int
    closed_actual_of_expected_closed: int
    policy_violations: int
    optout_retry_verdict: str
    optout_retry_provider_calls: int


def _service():
    sender = FakeSender(Channel.EMAIL)
    ledger = InMemoryLedger([ITEM], {ITEM.customer_id: {Channel.EMAIL: ADDR}})
    reg = InMemoryRegistry({ITEM.customer_id: {Channel.EMAIL}})
    return RecoveryService(ledger, reg, {Channel.EMAIL: sender}, FixedClock(NOW)), sender


def _run(v: Variant) -> Row:
    svc, _ = _service()
    th = svc.open_recovery(ITEM.item_id)
    svc.request_send(th, OutboundRequest(Channel.EMAIL, ADDR, "Please confirm the return.", Requester.HUMAN))
    res = svc.handle_reply(th, v.text)
    if res.proposed_posting is not None:
        svc.confirm_posting(th, res)
    state = th.state.value
    return Row(v.variant_id, v.expect, state, 1 if state == "HANDOFF" else 0, state == "CLOSED" and v.expect == "HANDOFF")


def _optout_check():
    svc, sender = _service()
    th = svc.open_recovery(ITEM.item_id)
    svc.request_send(th, OutboundRequest(Channel.EMAIL, ADDR, "Please confirm the return.", Requester.HUMAN))
    before = len(sender.calls)
    svc.handle_event(th, DeliveryEvent(EventKind.OPT_OUT, Channel.EMAIL, ADDR, NOW, None))
    out = svc.request_send(th, OutboundRequest(Channel.EMAIL, ADDR, "Reminder.", Requester.HUMAN))
    return out.verdict.verdict.value, len(sender.calls) - before


def evaluate() -> Report:
    rows = [_run(v) for v in VARIANTS]
    verdict, calls = _optout_check()
    closed = sum(r.final_state == "CLOSED" for r in rows)
    exp_closed = [r for r in rows if r.expect == "CLOSED"]
    violations = sum(r.violation for r in rows) + (1 if (verdict != "BLOCK" or calls != 0) else 0)
    return Report(rows, len(rows), closed, len(rows) - closed, closed / len(rows), len(exp_closed),
                  sum(r.final_state == "CLOSED" for r in exp_closed), violations, verdict, calls)


if __name__ == "__main__":
    rep = evaluate()
    for r in rep.rows:
        print(f"{r.variant_id:18} expect={r.expect:8} got={r.final_state:8} handoff_turn={r.handoff_turn} violation={r.violation}")
    print(f"k={rep.k} closed={rep.closed} ({rep.closed_rate:.0%}) handoff={rep.handoff} "
          f"expected-closed reached={rep.closed_actual_of_expected_closed}/{rep.closed_expected} "
          f"policy_violations={rep.policy_violations} optout_retry={rep.optout_retry_verdict} provider_calls={rep.optout_retry_provider_calls}")
