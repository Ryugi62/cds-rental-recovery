"""In-memory fakes for every port. Synthetic data only (SPEC non-goal: no real customer data)."""
from __future__ import annotations

from datetime import date, datetime
from typing import Dict, List, Optional

from application.ports import SendRecord
from domain.models import Channel, LedgerPosting, OutboundRequest, Requester, UnreturnedItem


class FixedClock:
    def __init__(self, now: datetime):
        self.now = now

    def now_local(self) -> datetime:
        return self.now


class FakeSender:
    def __init__(self, channel: Channel):
        self.channel = channel
        self.calls: List[OutboundRequest] = []

    def send(self, req: OutboundRequest) -> str:
        self.calls.append(req)
        return f"fake-{self.channel.value.lower()}-{len(self.calls)}"


class InMemoryLedger:
    def __init__(self, items: List[UnreturnedItem], contacts: Dict[str, Dict[Channel, str]]):
        self.items = {i.item_id: i for i in items}
        self.contacts = contacts
        self.postings: List[LedgerPosting] = []

    def get_item(self, item_id: str) -> UnreturnedItem:
        return self.items[item_id]

    def list_overdue(self, today: date) -> List[UnreturnedItem]:
        return [i for i in self.items.values() if i.quantity > 0 and i.due_date < today]

    def contact(self, customer_id: str, channel: Channel) -> Optional[str]:
        return self.contacts.get(customer_id, {}).get(channel)

    def post(self, posting: LedgerPosting) -> None:
        self.postings.append(posting)


class InMemoryRegistry:
    def __init__(self, consent: Optional[Dict[str, set]] = None):
        self._consent = consent or {}
        self._opt_out: set = set()
        self._blocked: set = set()
        self._sent: List[tuple] = []
        self._entries: List[dict] = []
        self._delivered: set = set()

    def consented(self, customer_id, channel):
        return channel in self._consent.get(customer_id, set())

    def opted_out(self, customer_id):
        return customer_id in self._opt_out

    def set_opted_out(self, customer_id):
        self._opt_out.add(customer_id)

    def address_blocked(self, address):
        return address in self._blocked

    def block_address(self, address):
        self._blocked.add(address)

    def sent_today(self, customer_id, day):
        return sum(1 for c, r in self._sent if c == customer_id and r.at.date() == day)

    def record_send(self, customer_id, rec: SendRecord):
        self._sent.append((customer_id, rec))

    def mark_delivered(self, message_id):
        self._delivered.add(message_id)

    def is_delivered(self, message_id) -> bool:
        return message_id in self._delivered

    def log(self, kind, detail):
        self._entries.append({"kind": kind, **detail})

    def entries(self):
        return list(self._entries)


class ScriptedAgent:
    """Stands in for an AgentCore agent: proposes whatever it was scripted to propose."""

    def __init__(self, proposals: List[OutboundRequest]):
        self.proposals = proposals

    def propose(self, item: UnreturnedItem) -> List[OutboundRequest]:
        return list(self.proposals)
