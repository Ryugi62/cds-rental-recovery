"""Thread state, events (SPEC G1, G6, G8, G9, G10)."""
from datetime import date, datetime
import pytest
from domain.models import (Channel, UnreturnedItem, ThreadState, EventKind, DeliveryEvent)
from domain.thread import RecoveryThread, open_thread, is_unreturned, IllegalTransition
from domain.events import decide_after_event, Decision


def item(qty=3, due=date(2026, 10, 15)):
    return UnreturnedItem("L-1", "c1", "camera", qty, due)


def test_unreturned_requires_overdue_and_qty():
    assert is_unreturned(item(), date(2026, 10, 22))
    assert not is_unreturned(item(qty=0), date(2026, 10, 22))
    assert not is_unreturned(item(due=date(2026, 10, 30)), date(2026, 10, 22))


def test_open_thread_state_open():
    t = open_thread(item(), date(2026, 10, 22), channels=[Channel.EMAIL, Channel.SMS])
    assert t.state is ThreadState.OPEN and t.quantity == 3


def test_open_thread_rejects_returned_item():
    with pytest.raises(ValueError):
        open_thread(item(qty=0), date(2026, 10, 22), channels=[Channel.EMAIL])


def test_sent_moves_to_waiting():
    t = open_thread(item(), date(2026, 10, 22), [Channel.EMAIL])
    t.mark_sent()
    assert t.state is ThreadState.WAITING


def test_close_only_from_waiting():
    t = open_thread(item(), date(2026, 10, 22), [Channel.EMAIL])
    with pytest.raises(IllegalTransition):
        t.close()
    t.mark_sent(); t.close()
    assert t.state is ThreadState.CLOSED


def test_handoff_records_reason():
    t = open_thread(item(), date(2026, 10, 22), [Channel.EMAIL])
    t.handoff("quantity_mismatch")
    assert t.state is ThreadState.HANDOFF and t.handoff_reason == "quantity_mismatch"


def test_closed_thread_cannot_handoff():
    t = open_thread(item(), date(2026, 10, 22), [Channel.EMAIL]); t.mark_sent(); t.close()
    with pytest.raises(IllegalTransition):
        t.handoff("x")


def ev(kind, ch=Channel.EMAIL):
    return DeliveryEvent(kind=kind, channel=ch, address="c1@example.test", at=datetime(2026, 10, 22, 12, 5))


def test_bounce_stops_address_and_suggests_sms():
    d = decide_after_event(ev(EventKind.BOUNCE), [Channel.EMAIL, Channel.SMS])
    assert d.block_address and d.suggest_channel is Channel.SMS and not d.handoff


def test_bounce_with_no_other_channel_hands_off():
    d = decide_after_event(ev(EventKind.BOUNCE), [Channel.EMAIL])
    assert d.suggest_channel is None and d.handoff


def test_opt_out_blocks_all_and_hands_off():
    d = decide_after_event(ev(EventKind.OPT_OUT), [Channel.EMAIL, Channel.SMS])
    assert d.opt_out_customer and d.handoff and d.suggest_channel is None


def test_delivery_starts_nudge_timer():
    d = decide_after_event(ev(EventKind.DELIVERY), [Channel.EMAIL])
    assert d.mark_delivered and d.nudge_after_hours == 24
