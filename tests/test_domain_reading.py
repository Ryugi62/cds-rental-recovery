"""Reply reading (SPEC G5, G7)."""
from datetime import date
from domain.reading import read_reply, compare_with_ledger
from domain.models import UnreturnedItem

TODAY = date(2026, 10, 22)  # Thursday


def test_korean_thursday_three_units():
    r = read_reply("목요일에 3개 반납할게요", TODAY)
    assert r.quantity == 3 and r.return_date == date(2026, 10, 29) and r.confidence >= 0.8


def test_english_thursday_three_units():
    r = read_reply("I'll bring back 3 on Thursday", TODAY)
    assert r.quantity == 3 and r.return_date == date(2026, 10, 29)


def test_tomorrow_keyword():
    r = read_reply("Tomorrow, 2 units", TODAY)
    assert r.return_date == date(2026, 10, 23) and r.quantity == 2


def test_explicit_iso_date():
    r = read_reply("Returning 4 on 2026-10-30", TODAY)
    assert r.return_date == date(2026, 10, 30) and r.quantity == 4


def test_no_quantity_means_low_confidence():
    r = read_reply("I'll return them soon", TODAY)
    assert r.quantity is None and r.confidence < 0.5


def test_no_date_means_low_confidence():
    r = read_reply("I have 3 here", TODAY)
    assert r.return_date is None and r.confidence < 0.8


def test_empty_text_zero_confidence():
    assert read_reply("", TODAY).confidence == 0.0


def test_compare_match():
    item = UnreturnedItem("L-1", "c1", "camera", 3, date(2026, 10, 15))
    c = compare_with_ledger(read_reply("Thursday 3 units", TODAY), item)
    assert c.matches and c.reason == "match"


def test_compare_quantity_mismatch():
    item = UnreturnedItem("L-1", "c1", "camera", 5, date(2026, 10, 15))
    c = compare_with_ledger(read_reply("Thursday 3 units", TODAY), item)
    assert not c.matches and c.reason == "quantity_mismatch"


def test_compare_low_confidence():
    item = UnreturnedItem("L-1", "c1", "camera", 3, date(2026, 10, 15))
    c = compare_with_ledger(read_reply("soon", TODAY), item)
    assert not c.matches and c.reason == "low_confidence"
