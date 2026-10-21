"""Reply reading: pull return date and quantity out of a customer reply (Korean or English)."""
from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Optional

from .models import Comparison, ReplyReading, UnreturnedItem

CONFIDENT = 0.8
_WEEKDAYS = [("월", r"mon(day)?"), ("화", r"tue(s|sday)?"), ("수", r"wed(nesday)?"), ("목", r"thu(r|rs|rsday)?"),
             ("금", r"fri(day)?"), ("토", r"saturday"), ("일", r"sunday")]
_ISO = re.compile(r"(\d{4})-(\d{2})-(\d{2})")


def _weekday(text: str) -> Optional[int]:
    low = text.lower()
    for i, (ko, en) in enumerate(_WEEKDAYS):
        if f"{ko}요일" in text or re.search(rf"\b{en}\b", low):
            return i
    return None


def _date(text: str, today: date) -> Optional[date]:
    m = _ISO.search(text)
    if m:
        try:
            return date(int(m[1]), int(m[2]), int(m[3]))
        except ValueError:
            return None
    low = text.lower()
    if "tomorrow" in low or "내일" in text:
        return today + timedelta(days=1)
    if "today" in low or "오늘" in text:
        return today
    wd = _weekday(text)
    if wd is not None:
        return today + timedelta(days=(wd - today.weekday() - 1) % 7 + 1)
    return None


def _quantity(text: str) -> Optional[int]:
    stripped = _ISO.sub(" ", text)
    m = re.search(r"(\d+)\s*(개|대|units?|pcs|pieces|items?|cameras?)", stripped, re.I) or re.search(r"\b(\d+)\b", stripped)
    return int(m[1]) if m else None


def read_reply(text: str, today: date) -> ReplyReading:
    if not text or not text.strip():
        return ReplyReading(None, None, 0.0, text or "")
    d, q = _date(text, today), _quantity(text)
    conf = 0.9 if (d and q is not None) else 0.4 if (d or q is not None) else 0.0
    return ReplyReading(q, d, conf, text)


def compare_with_ledger(reading: ReplyReading, item: UnreturnedItem) -> Comparison:
    if reading.confidence < CONFIDENT or reading.quantity is None or reading.return_date is None:
        return Comparison(False, "low_confidence")
    if reading.quantity != item.quantity:
        return Comparison(False, "quantity_mismatch")
    return Comparison(True, "match")
