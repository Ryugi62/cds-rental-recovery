"""Gate policies (SPEC G2, G3, G4, G9). Times are passed in; domain never reads a clock."""
from datetime import datetime
from domain.models import Channel, OutboundRequest, Requester, Verdict
from domain.gate import GateContext, evaluate

NOON = datetime(2026, 10, 22, 12, 0)


def req(text="Hi, please confirm the return of 3 cameras.", channel=Channel.EMAIL, by=Requester.HUMAN):
    return OutboundRequest(channel=channel, recipient="c1@example.test", text=text, requested_by=by)


def ctx(**kw):
    base = dict(now_local=NOON, sent_today=0, opted_out=False, consented=True, address_blocked=False)
    base.update(kw)
    return GateContext(**base)


def test_pass_when_consented_daytime_under_cap():
    v = evaluate(req(), ctx())
    assert v.verdict is Verdict.PASS and v.reason == "ok"


def test_block_when_daily_cap_reached():
    v = evaluate(req(), ctx(sent_today=2))
    assert v.verdict is Verdict.BLOCK and v.reason == "daily_cap"


def test_cap_is_two_per_day_boundary():
    assert evaluate(req(), ctx(sent_today=1)).verdict is Verdict.PASS


def test_hold_in_quiet_hours_with_release_time_morning():
    v = evaluate(req(), ctx(now_local=datetime(2026, 10, 22, 22, 30)))
    assert v.verdict is Verdict.HOLD and v.reason == "quiet_hours"
    assert v.release_at == datetime(2026, 10, 23, 8, 0)


def test_hold_early_morning_releases_same_day():
    v = evaluate(req(), ctx(now_local=datetime(2026, 10, 22, 6, 0)))
    assert v.release_at == datetime(2026, 10, 22, 8, 0)


def test_quiet_hours_boundaries():
    assert evaluate(req(), ctx(now_local=datetime(2026, 10, 22, 8, 0))).verdict is Verdict.PASS
    assert evaluate(req(), ctx(now_local=datetime(2026, 10, 22, 21, 0))).verdict is Verdict.HOLD


def test_approval_for_large_amount_text():
    v = evaluate(req(text="Your balance of $4,500 is overdue."), ctx())
    assert v.verdict is Verdict.APPROVAL and v.reason == "needs_approval"


def test_approval_for_legal_threat_phrase():
    v = evaluate(req(text="We will take legal action."), ctx())
    assert v.verdict is Verdict.APPROVAL


def test_approved_request_passes_approval_gate():
    v = evaluate(req(text="Your balance of $4,500 is overdue."), ctx(human_approved=True))
    assert v.verdict is Verdict.PASS


def test_block_when_opted_out_beats_everything():
    v = evaluate(req(), ctx(opted_out=True, sent_today=0))
    assert v.verdict is Verdict.BLOCK and v.reason == "opt_out"


def test_block_when_no_consent():
    assert evaluate(req(), ctx(consented=False)).reason == "no_consent"


def test_block_when_address_bounced():
    v = evaluate(req(), ctx(address_blocked=True))
    assert v.verdict is Verdict.BLOCK and v.reason == "address_blocked"


def test_agent_request_gets_same_gate_g11():
    v = evaluate(req(by=Requester.AGENT), ctx(sent_today=2))
    assert v.verdict is Verdict.BLOCK and v.requested_by is Requester.AGENT


def test_agent_cannot_self_approve():
    v = evaluate(req(text="Balance $9,000 overdue", by=Requester.AGENT), ctx(human_approved=False))
    assert v.verdict is Verdict.APPROVAL


def test_priority_opt_out_over_quiet_hours():
    v = evaluate(req(), ctx(opted_out=True, now_local=datetime(2026, 10, 22, 23, 0)))
    assert v.reason == "opt_out"
