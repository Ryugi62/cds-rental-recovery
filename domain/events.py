"""Delivery events change the next decision."""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from .models import Channel, DeliveryEvent, EventKind

NUDGE_HOURS = 24


@dataclass(frozen=True)
class Decision:
    block_address: bool = False
    opt_out_customer: bool = False
    suggest_channel: Optional[Channel] = None
    handoff: bool = False
    mark_delivered: bool = False
    nudge_after_hours: Optional[int] = None
    note: str = ""


def decide_after_event(ev: DeliveryEvent, channels: List[Channel]) -> Decision:
    if ev.kind is EventKind.OPT_OUT:
        return Decision(opt_out_customer=True, handoff=True, note="customer opted out; all sends blocked")
    if ev.kind is EventKind.BOUNCE:
        others = [c for c in channels if c is not ev.channel]
        if others:
            return Decision(block_address=True, suggest_channel=others[0], note=f"{ev.channel.value} bounced; try {others[0].value}")
        return Decision(block_address=True, handoff=True, note="bounced and no other channel")
    return Decision(mark_delivered=True, nudge_after_hours=NUDGE_HOURS, note="delivered; nudge timer started")
