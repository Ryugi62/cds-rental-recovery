"""Ubiquitous-language types (SPEC section 5). No I/O, no SDK, no clock."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import Optional


class Channel(str, Enum):
    EMAIL = "EMAIL"
    SMS = "SMS"


class Requester(str, Enum):
    HUMAN = "HUMAN"
    AGENT = "AGENT"


class Verdict(str, Enum):
    PASS = "PASS"
    HOLD = "HOLD"
    BLOCK = "BLOCK"
    APPROVAL = "APPROVAL"


class ThreadState(str, Enum):
    OPEN = "OPEN"
    WAITING = "WAITING"
    CLOSED = "CLOSED"
    HANDOFF = "HANDOFF"


class EventKind(str, Enum):
    DELIVERY = "DELIVERY"
    BOUNCE = "BOUNCE"
    OPT_OUT = "OPT_OUT"


@dataclass(frozen=True)
class UnreturnedItem:
    item_id: str
    customer_id: str
    equipment: str
    quantity: int
    due_date: date


@dataclass(frozen=True)
class OutboundRequest:
    channel: Channel
    recipient: str
    text: str
    requested_by: Requester


@dataclass(frozen=True)
class GateVerdict:
    verdict: Verdict
    reason: str
    channel: Channel
    requested_by: Requester
    release_at: Optional[datetime] = None


@dataclass(frozen=True)
class ReplyReading:
    quantity: Optional[int]
    return_date: Optional[date]
    confidence: float
    raw: str = ""


@dataclass(frozen=True)
class Comparison:
    matches: bool
    reason: str  # match | quantity_mismatch | low_confidence


@dataclass(frozen=True)
class DeliveryEvent:
    kind: EventKind
    channel: Channel
    address: str
    at: datetime


@dataclass(frozen=True)
class LedgerPosting:
    item_id: str
    return_date: date
    quantity: int
