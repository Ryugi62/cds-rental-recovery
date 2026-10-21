"""Composition root for the gate screen: runs one synthetic case through the real RecoveryService with fakes."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import List, Optional

from adapters.fakes import FakeSender, FixedClock, InMemoryLedger, InMemoryRegistry, ScriptedAgent
from application.service import RecoveryService
from domain.events import Decision
from domain.models import (Channel, Comparison, DeliveryEvent, EventKind, GateVerdict, LedgerPosting, OutboundRequest,
                           ReplyReading, Requester, ThreadState, UnreturnedItem)

DEFAULT_REPLY = "I'll bring back 3 on Thursday"
ITEM = UnreturnedItem("L-104", "C-104", "Cinema camera kit", 3, date(2026, 10, 15))
EMAIL = "customer@example.test"
PHONE = "+1 555 0100"


@dataclass
class Step:
    title: str
    body: str
    at: datetime
    thread_state: ThreadState
    verdict: Optional[GateVerdict] = None
    request: Optional[OutboundRequest] = None
    event: Optional[DeliveryEvent] = None
    decision: Optional[Decision] = None
    reading: Optional[ReplyReading] = None
    comparison: Optional[Comparison] = None
    reply_input: bool = False
    handoff_reason: Optional[str] = None
    ledger_rows: List[LedgerPosting] = field(default_factory=list)
    sender_calls_delta: int = 0
    sms_sent: int = 0
    email_sent: int = 0
    note: str = ""


@dataclass
class Story:
    name: str
    steps: List[Step]
    reply_text: str = DEFAULT_REPLY


class _Recorder:
    def __init__(self, service, clock, sms, email, ledger):
        self.s, self.clock, self.sms, self.email, self.ledger = service, clock, sms, email, ledger
        self.thread = None
        self.steps: List[Step] = []

    def _calls(self):
        return len(self.sms.calls) + len(self.email.calls)

    def add(self, title, body, **kw) -> Step:
        st = Step(title=title, body=body, at=self.clock.now, thread_state=self.thread.state,
                  ledger_rows=list(self.ledger.postings), sms_sent=len(self.sms.calls), email_sent=len(self.email.calls),
                  handoff_reason=self.thread.handoff_reason, **kw)
        self.steps.append(st)
        return st

    def send(self, title, body, req, approve_index=None):
        before = self._calls()
        if approve_index is not None:
            req = self.s.pending_approvals[approve_index][1]
        out = self.s.approve(approve_index) if approve_index is not None else self.s.request_send(self.thread, req)
        st = self.add(title, body, verdict=out.verdict, request=req)
        st.sender_calls_delta = self._calls() - before
        return out

    def event(self, title, body, ev, message_id=None):
        d = self.s.handle_event(self.thread, ev, message_id)
        self.add(title, body, event=ev, decision=d)


def _setup(now: datetime, agent=None):
    ledger = InMemoryLedger([ITEM], {"C-104": {Channel.EMAIL: EMAIL, Channel.SMS: PHONE}})
    reg = InMemoryRegistry({"C-104": {Channel.EMAIL, Channel.SMS}})
    sms, email, clock = FakeSender(Channel.SMS), FakeSender(Channel.EMAIL), FixedClock(now)
    svc = RecoveryService(ledger, reg, {Channel.SMS: sms, Channel.EMAIL: email}, clock, agent)
    rec = _Recorder(svc, clock, sms, email, ledger)
    rec.thread = svc.open_recovery("L-104")
    return rec


def _req(channel, to, text, by=Requester.HUMAN):
    return OutboundRequest(channel, to, text, by)


def build_story(reply_text: str = DEFAULT_REPLY) -> Story:
    rec = _setup(datetime(2026, 10, 22, 12, 0))
    rec.add("An overdue item opens a recovery thread",
            "3 cinema camera kits were due Oct 15. The thread opens with the channels this customer agreed to.")
    rec.send("Text message goes first", "Customers answer texts fastest. The gate checks consent, cap and hours before anything is sent.",
             _req(Channel.SMS, PHONE, "Hi, this is Sample Rentals. Can you confirm when the 3 camera kits come back?"))
    rec.event("The text bounces back", "The carrier reports the number unreachable. The number is stopped and the next channel is suggested.",
              DeliveryEvent(EventKind.BOUNCE, Channel.SMS, PHONE, rec.clock.now, "fake-sms-1"), "fake-sms-1")
    rec.clock.now = datetime(2026, 10, 22, 22, 10)
    rec.send("Email at night is held", "The email is ready at 22:10. Quiet hours run 21:00 to 08:00, so nothing leaves yet.",
             _req(Channel.EMAIL, EMAIL, "Hello, a quick check on the 3 camera kits due Oct 15. When can you return them?"))
    rec.clock.now = datetime(2026, 10, 23, 8, 5)
    rec.send("A large balance needs a person", "The draft mentions a $4,500 balance. Money wording waits for a human decision.",
             _req(Channel.EMAIL, EMAIL, "Hello, the 3 camera kits are overdue and a balance of $4,500 is open. When can you return them?"))
    out = rec.send("A person approves, the email goes", "After approval the gate runs again and passes. One send, one record.",
                   None, approve_index=0)
    mid = out.message_id
    rec.event("Delivery confirmed", "The delivery event marks the send as delivered and starts a 24 hour nudge timer.",
              DeliveryEvent(EventKind.DELIVERY, Channel.EMAIL, EMAIL, rec.clock.now, mid), mid)
    rec.send("The agent nudges once more", "An AI agent proposes a reminder. It uses the same gate as a person.",
             _req(Channel.EMAIL, EMAIL, "Friendly reminder about the 3 camera kits.", Requester.AGENT))
    rec.send("The agent tries a third time", "Two sends today is the cap. The gate blocks it and the sender is never called.",
             _req(Channel.EMAIL, EMAIL, "Reminder again, please reply today.", Requester.AGENT))
    res = rec.s.handle_reply(rec.thread, reply_text)
    rec.add("The customer replies", "The reply is read for a return date and a quantity, then checked against the ledger.",
            reading=res.reading, comparison=res.comparison, reply_input=True)
    if res.proposed_posting is not None:
        rec.s.confirm_posting(rec.thread, res)
        rec.add("Ledger updated, thread closed", "The confirmed reading becomes one ledger row. The case is done.")
    else:
        rec.steps[-1].note = "Nothing is written to the ledger. A person gets this item with the reason shown above."
    return Story("Return confirmed", rec.steps, reply_text)


def build_optout_story() -> Story:
    rec = _setup(datetime(2026, 10, 22, 12, 0))
    rec.add("An overdue item opens a recovery thread", "Same synthetic customer, a different ending.")
    out = rec.send("Text message goes first", "The gate passes the first text.",
                   _req(Channel.SMS, PHONE, "Hi, this is Sample Rentals. Can you confirm when the 3 camera kits come back?"))
    rec.event("The customer replies STOP", "An opt-out event arrives. Every channel is closed and a person takes over.",
              DeliveryEvent(EventKind.OPT_OUT, Channel.SMS, PHONE, rec.clock.now, out.message_id), out.message_id)
    rec.send("The agent tries email anyway", "The gate blocks it. No sender is called.",
             _req(Channel.EMAIL, EMAIL, "Just checking in on the camera kits.", Requester.AGENT))
    return Story("Customer opted out", rec.steps)
