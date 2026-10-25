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


ASSIST_WINDOW_DAYS = 60
_EN_NUM = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve"]
# Korean: determiner forms need a counter ("세 개"; "세 시" is a clock time), standalone forms need a boundary.
_KO_DET = {1: "한", 2: "두", 3: "세", 4: "네", 5: "다섯", 6: "여섯", 7: "일곱", 8: "여덟", 9: "아홉", 10: "열"}
_KO_ALONE = {1: "하나", 2: "둘", 3: "셋", 4: "넷", 5: "다섯", 6: "여섯", 7: "일곱", 8: "여덟", 9: "아홉", 10: "열"}
_ALL = re.compile(r"\ball\b|\bevery(thing| one)\b|\bthe (whole|entire) (lot|order)\b|전부|모두|다 (반납|갖다|가져)", re.I)


def _quantity_in_text(text: str, qty: int) -> bool:
    if re.search(rf"(?<!\d){qty}(?!\d)", _ISO.sub(" ", text)):
        return True
    if 0 <= qty < len(_EN_NUM) and re.search(rf"\b{_EN_NUM[qty]}\b", text, re.I):
        return True
    det, alone = _KO_DET.get(qty), _KO_ALONE.get(qty)
    if det and re.search(rf"(^|\s){det}\s?(개|대|박스|세트|가지)", text):
        return True
    return bool(alone and re.search(rf"(^|\s){alone}(\s|$|[.,!?]|(다|만|도|를|은|이|요))", text))


def ground_suggestion(text: str, today: date, quantity: Optional[int], return_date: Optional[date],
                      ledger_quantity: int, all_units: bool = False) -> ReplyReading:
    """Accept a model's answer only where the customer's own words support it (no invented numbers)."""
    q: Optional[int] = None
    if all_units and _ALL.search(text):
        q = ledger_quantity
    elif isinstance(quantity, int) and quantity >= 0 and _quantity_in_text(text, quantity):
        q = quantity
    d = return_date if (return_date and today <= return_date <= today + timedelta(days=ASSIST_WINDOW_DAYS)) else None
    conf = 0.85 if (q is not None and d) else 0.4 if (q is not None or d) else 0.0
    return ReplyReading(q, d, conf, text, "assist")


def compare_with_ledger(reading: ReplyReading, item: UnreturnedItem) -> Comparison:
    if reading.confidence < CONFIDENT or reading.quantity is None or reading.return_date is None:
        return Comparison(False, "low_confidence")
    if reading.quantity != item.quantity:
        return Comparison(False, "quantity_mismatch")
    return Comparison(True, "match")
