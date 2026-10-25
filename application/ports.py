"""Ports the use cases depend on. Adapters implement them."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import List, Optional, Protocol

from domain.models import Channel, LedgerPosting, OutboundRequest, UnreturnedItem


@dataclass(frozen=True)
class SendRecord:
    message_id: str
    recipient: str
    channel: Channel
    at: datetime
    delivered: bool = False


@dataclass(frozen=True)
class InboundMail:
    sender: str
    subject: str
    text: str
    message_id: str


@dataclass(frozen=True)
class AssistSuggestion:
    """What a language model proposes for a low-confidence reply. Untrusted until grounded by the domain."""
    quantity: Optional[int]
    return_date: Optional[date]
    follow_up: Optional[str]
    model: str
    all_units: bool = False


class ReplyAssistant(Protocol):
    def suggest(self, text: str, today: date) -> AssistSuggestion: ...


class Clock(Protocol):
    def now_local(self) -> datetime: ...


class Sender(Protocol):
    channel: Channel

    def send(self, req: OutboundRequest) -> str:
        """Return a provider message id."""


class Ledger(Protocol):
    def get_item(self, item_id: str) -> UnreturnedItem: ...
    def list_overdue(self, today: date) -> List[UnreturnedItem]: ...
    def contact(self, customer_id: str, channel: Channel) -> Optional[str]: ...
    def post(self, posting: LedgerPosting) -> None: ...


class Registry(Protocol):
    """Consent, opt-out, blocked addresses, send and block history."""
    def consented(self, customer_id: str, channel: Channel) -> bool: ...
    def opted_out(self, customer_id: str) -> bool: ...
    def set_opted_out(self, customer_id: str) -> None: ...
    def address_blocked(self, address: str) -> bool: ...
    def block_address(self, address: str) -> None: ...
    def sent_today(self, customer_id: str, day: date) -> int: ...
    def record_send(self, customer_id: str, rec: SendRecord) -> None: ...
    def mark_delivered(self, message_id: str) -> None: ...
    def log(self, kind: str, detail: dict) -> None: ...
    def entries(self) -> List[dict]: ...


class Agent(Protocol):
    def propose(self, item: UnreturnedItem) -> List[OutboundRequest]: ...
