"""Use cases against fakes: SPEC G1-G11."""
from datetime import date, datetime
import pytest
from adapters.fakes import FakeSender, FixedClock, InMemoryLedger, InMemoryRegistry, ScriptedAgent
from application.service import RecoveryService
from domain.models import (Channel, DeliveryEvent, EventKind, OutboundRequest, Requester, ThreadState,
                           UnreturnedItem, Verdict)

NOON = datetime(2026, 10, 22, 12, 0)
ITEM = UnreturnedItem("L-1", "c1", "camera", 3, date(2026, 10, 15))


def build(now=NOON, agent=None):
    ledger = InMemoryLedger([ITEM], {"c1": {Channel.EMAIL: "c1@example.test", Channel.SMS: "+10000000001"}})
    reg = InMemoryRegistry({"c1": {Channel.EMAIL, Channel.SMS}})
    email, sms = FakeSender(Channel.EMAIL), FakeSender(Channel.SMS)
    svc = RecoveryService(ledger, reg, {Channel.EMAIL: email, Channel.SMS: sms}, FixedClock(now), agent)
    return svc, ledger, reg, email, sms


def mail(text="Please confirm the return of 3 cameras.", by=Requester.HUMAN):
    return OutboundRequest(Channel.EMAIL, "c1@example.test", text, by)


def test_g1_open_recovery_thread_lists_channels_and_quantity():
    svc, *_ = build()
    t = svc.open_recovery("L-1")
    assert t.state is ThreadState.OPEN and t.quantity == 3
    assert set(t.channels) == {Channel.EMAIL, Channel.SMS}


def test_g1_not_overdue_item_cannot_open():
    svc, ledger, *_ = build()
    ledger.items["L-1"] = UnreturnedItem("L-1", "c1", "camera", 0, date(2026, 10, 15))
    with pytest.raises(ValueError):
        svc.open_recovery("L-1")


def test_g2_pass_sends_once_and_records():
    svc, _, reg, email, _ = build()
    t = svc.open_recovery("L-1")
    out = svc.request_send(t, mail())
    assert out.verdict.verdict is Verdict.PASS and len(email.calls) == 1
    assert t.state is ThreadState.WAITING
    assert reg.sent_today("c1", NOON.date()) == 1


def test_g3_third_send_blocked_no_sender_call():
    svc, _, reg, email, _ = build()
    t = svc.open_recovery("L-1")
    svc.request_send(t, mail()); svc.request_send(t, mail())
    out = svc.request_send(t, mail())
    assert out.verdict.verdict is Verdict.BLOCK and out.verdict.reason == "daily_cap"
    assert len(email.calls) == 2
    assert [e["kind"] for e in reg.entries()].count("BLOCK") == 1


def test_g4_quiet_hours_hold_no_send():
    svc, _, _, email, _ = build(now=datetime(2026, 10, 22, 22, 0))
    t = svc.open_recovery("L-1")
    out = svc.request_send(t, mail())
    assert out.verdict.verdict is Verdict.HOLD and out.verdict.release_at == datetime(2026, 10, 23, 8, 0)
    assert email.calls == []


def test_g4_approval_waits_for_human_then_sends():
    svc, _, _, email, _ = build()
    t = svc.open_recovery("L-1")
    out = svc.request_send(t, mail("Your balance of $4,500 is overdue."))
    assert out.verdict.verdict is Verdict.APPROVAL and email.calls == []
    assert len(svc.pending_approvals) == 1
    done = svc.approve(0)
    assert done.verdict.verdict is Verdict.PASS and len(email.calls) == 1
    assert svc.pending_approvals == []


def test_g5_reply_match_proposes_posting_not_written():
    svc, ledger, *_ = build()
    t = svc.open_recovery("L-1"); svc.request_send(t, mail())
    res = svc.handle_reply(t, "목요일에 3개 반납할게요")
    assert res.comparison.matches and res.proposed_posting.quantity == 3
    assert ledger.postings == []


def test_g6_confirm_posting_closes_thread():
    svc, ledger, *_ = build()
    t = svc.open_recovery("L-1"); svc.request_send(t, mail())
    res = svc.handle_reply(t, "목요일에 3개 반납할게요")
    svc.confirm_posting(t, res)
    assert len(ledger.postings) == 1 and ledger.postings[0].return_date == date(2026, 10, 29)
    assert t.state is ThreadState.CLOSED


def test_g7_mismatch_hands_off_with_reason_no_posting():
    svc, ledger, *_ = build()
    t = svc.open_recovery("L-1"); svc.request_send(t, mail())
    res = svc.handle_reply(t, "Thursday, 2 units")
    assert res.proposed_posting is None and t.state is ThreadState.HANDOFF
    assert t.handoff_reason == "quantity_mismatch" and ledger.postings == []


def test_g7_low_confidence_hands_off():
    svc, *_ = build()
    t = svc.open_recovery("L-1"); svc.request_send(t, mail())
    svc.handle_reply(t, "soon")
    assert t.handoff_reason == "low_confidence"


def test_g7_confirm_without_match_rejected():
    svc, *_ = build()
    t = svc.open_recovery("L-1"); svc.request_send(t, mail())
    res = svc.handle_reply(t, "soon")
    with pytest.raises(ValueError):
        svc.confirm_posting(t, res)


def ev(kind, ch=Channel.EMAIL, addr="c1@example.test"):
    return DeliveryEvent(kind, ch, addr, NOON)


def test_g8_bounce_blocks_address_and_suggests_sms():
    svc, _, reg, email, _ = build()
    t = svc.open_recovery("L-1"); svc.request_send(t, mail())
    d = svc.handle_event(t, ev(EventKind.BOUNCE))
    assert d.suggest_channel is Channel.SMS
    out = svc.request_send(t, mail())
    assert out.verdict.reason == "address_blocked" and len(email.calls) == 1


def test_g9_opt_out_blocks_every_channel_and_hands_off():
    svc, _, _, email, sms = build()
    t = svc.open_recovery("L-1"); svc.request_send(t, mail())
    svc.handle_event(t, ev(EventKind.OPT_OUT))
    out = svc.request_send(t, OutboundRequest(Channel.SMS, "+10000000001", "hello", Requester.HUMAN))
    assert out.verdict.reason == "opt_out" and sms.calls == []
    assert t.state is ThreadState.HANDOFF


def test_g10_delivery_marks_record_and_returns_nudge():
    svc, _, reg, *_ = build()
    t = svc.open_recovery("L-1"); out = svc.request_send(t, mail())
    d = svc.handle_event(t, ev(EventKind.DELIVERY), message_id=out.message_id)
    assert reg.is_delivered(out.message_id) and d.nudge_after_hours == 24


def test_g11_agent_proposals_go_through_gate():
    agent = ScriptedAgent([mail(by=Requester.AGENT)] * 3)
    svc, _, _, email, _ = build(agent=agent)
    t = svc.open_recovery("L-1")
    outs = svc.run_agent(t)
    assert [o.verdict.verdict for o in outs] == [Verdict.PASS, Verdict.PASS, Verdict.BLOCK]
    assert len(email.calls) == 2


def test_g11_no_path_to_sender_except_gate():
    import inspect, application.service as s
    src = inspect.getsource(s)
    assert src.count(".send(") == 1  # the single dispatch point sits after the gate
