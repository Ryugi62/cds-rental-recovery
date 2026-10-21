"""RecoveryThread state machine."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import List, Optional

from .models import Channel, ThreadState, UnreturnedItem


class IllegalTransition(Exception):
    pass


def is_unreturned(item: UnreturnedItem, today: date) -> bool:
    return item.quantity > 0 and item.due_date < today


@dataclass
class RecoveryThread:
    item: UnreturnedItem
    channels: List[Channel]
    state: ThreadState = ThreadState.OPEN
    handoff_reason: Optional[str] = None

    @property
    def quantity(self) -> int:
        return self.item.quantity

    def mark_sent(self) -> None:
        if self.state not in (ThreadState.OPEN, ThreadState.WAITING):
            raise IllegalTransition(f"cannot send from {self.state.value}")
        self.state = ThreadState.WAITING

    def close(self) -> None:
        if self.state is not ThreadState.WAITING:
            raise IllegalTransition(f"cannot close from {self.state.value}")
        self.state = ThreadState.CLOSED

    def handoff(self, reason: str) -> None:
        if self.state is ThreadState.CLOSED:
            raise IllegalTransition("closed thread cannot hand off")
        self.state = ThreadState.HANDOFF
        self.handoff_reason = reason


def open_thread(item: UnreturnedItem, today: date, channels: List[Channel]) -> RecoveryThread:
    if not is_unreturned(item, today):
        raise ValueError("item is not an overdue unreturned item")
    return RecoveryThread(item=item, channels=list(channels))
