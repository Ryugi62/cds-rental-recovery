"""Use cases. Every send, human or agent, passes through _gate_and_dispatch (the only .send call)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from domain.events import Decision, decide_after_event
from domain.gate import GateContext, evaluate
from domain.models import (Channel, Comparison, DeliveryEvent, GateVerdict, LedgerPosting, OutboundRequest,
                           ReplyReading, Verdict)
from domain.reading import compare_with_ledger, read_reply
from domain.thread import RecoveryThread, open_thread, is_unreturned
from .ports import Agent, Clock, Ledger, Registry, Sender, SendRecord


@dataclass(frozen=True)
class SendOutcome:
    verdict: GateVerdict
    message_id: Optional[str] = None
    send_error: Optional[str] = None


@dataclass(frozen=True)
class ReplyResult:
    reading: ReplyReading
    comparison: Comparison
    proposed_posting: Optional[LedgerPosting]


class RecoveryService:
    def __init__(self, ledger: Ledger, registry: Registry, senders: Dict[Channel, Sender], clock: Clock,
                 agent: Optional[Agent] = None):
        self.ledger, self.registry, self.senders, self.clock, self.agent = ledger, registry, senders, clock, agent
        self.pending_approvals: List[Tuple[RecoveryThread, OutboundRequest]] = []
        self.held: List[Tuple[RecoveryThread, OutboundRequest, GateVerdict]] = []

    def open_recovery(self, item_id: str) -> RecoveryThread:
        item = self.ledger.get_item(item_id)
        today = self.clock.now_local().date()
        if not is_unreturned(item, today):
            raise ValueError("item is not an overdue unreturned item")
        channels = [c for c in (Channel.EMAIL, Channel.SMS)
                    if self.ledger.contact(item.customer_id, c) and self.registry.consented(item.customer_id, c)]
        self.registry.log("OPEN", {"item": item_id, "channels": [c.value for c in channels]})
        return open_thread(item, today, channels)

    def request_send(self, thread: RecoveryThread, req: OutboundRequest) -> SendOutcome:
        return self._gate_and_dispatch(thread, req, human_approved=False)

    def approve(self, index: int) -> SendOutcome:
        thread, req = self.pending_approvals.pop(index)
        return self._gate_and_dispatch(thread, req, human_approved=True)

    def run_agent(self, thread: RecoveryThread) -> List[SendOutcome]:
        if self.agent is None:
            return []
        return [self.request_send(thread, r) for r in self.agent.propose(thread.item)]

    def _gate_and_dispatch(self, thread: RecoveryThread, req: OutboundRequest, human_approved: bool) -> SendOutcome:
        cust, now = thread.item.customer_id, self.clock.now_local()
        ctx = GateContext(
            now_local=now,
            sent_today=self.registry.sent_today(cust, now.date()),
            opted_out=self.registry.opted_out(cust),
            consented=self.registry.consented(cust, req.channel),
            address_blocked=self.registry.address_blocked(req.recipient),
            human_approved=human_approved,
        )
        verdict = evaluate(req, ctx)
        self.registry.log(verdict.verdict.value, {"item": thread.item.item_id, "reason": verdict.reason,
                                                  "channel": req.channel.value, "by": req.requested_by.value})
        if verdict.verdict is Verdict.APPROVAL:
            self.pending_approvals.append((thread, req))
        elif verdict.verdict is Verdict.HOLD:
            self.held.append((thread, req, verdict))
        elif verdict.verdict is Verdict.PASS:
            try:
                mid = self.senders[req.channel].send(req)
            except Exception as exc:  # provider error, throttling, network: never silent, never retried blindly
                err = f"{type(exc).__name__}: {exc}"
                self.registry.log("SEND_FAILED", {"item": thread.item.item_id, "channel": req.channel.value,
                                                  "error": err})
                thread.handoff("send_failed")
                return SendOutcome(verdict, None, err)
            self.registry.record_send(cust, SendRecord(mid, req.recipient, req.channel, now))
            thread.mark_sent()
            return SendOutcome(verdict, mid)
        return SendOutcome(verdict)

    def handle_reply(self, thread: RecoveryThread, text: str) -> ReplyResult:
        reading = read_reply(text, self.clock.now_local().date())
        cmp = compare_with_ledger(reading, thread.item)
        self.registry.log("READ", {"item": thread.item.item_id, "match": cmp.matches, "reason": cmp.reason,
                                   "confidence": reading.confidence})
        if not cmp.matches:
            thread.handoff(cmp.reason)
            return ReplyResult(reading, cmp, None)
        return ReplyResult(reading, cmp, LedgerPosting(thread.item.item_id, reading.return_date, reading.quantity))

    def confirm_posting(self, thread: RecoveryThread, result: ReplyResult) -> None:
        if result.proposed_posting is None:
            raise ValueError("no matching reading to post; hand-off item exists instead")
        self.ledger.post(result.proposed_posting)
        thread.close()
        self.registry.log("POSTED", {"item": thread.item.item_id, "qty": result.proposed_posting.quantity})

    def handle_event(self, thread: RecoveryThread, ev: DeliveryEvent, message_id: Optional[str] = None) -> Decision:
        d = decide_after_event(ev, thread.channels)
        if d.block_address:
            self.registry.block_address(ev.address)
        if d.opt_out_customer:
            self.registry.set_opted_out(thread.item.customer_id)
        if d.mark_delivered and message_id:
            self.registry.mark_delivered(message_id)
        if d.handoff:
            thread.handoff(ev.kind.value.lower())
        self.registry.log(ev.kind.value, {"item": thread.item.item_id, "note": d.note})
        return d
