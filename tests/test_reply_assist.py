"""G13: reply-reading assist (Amazon Bedrock behind a port). Fakes only; no network, no boto3 calls.

Rules under test:
- the assist is called only when the regex reading is below CONFIDENT;
- a model answer is used only if it is grounded in the customer's own words (no invented quantities, date in window);
- a follow-up question the model drafts is an OutboundRequest by AGENT and goes through the same gate;
- an assist failure is logged and ends in a hand-off, never a silent pass.
"""
import json
from datetime import date, datetime, timedelta

import pytest

from adapters.bedrock import AssistError, BedrockReplyAssistant
from adapters.fakes import FakeSender, FixedClock, InMemoryLedger, InMemoryRegistry
from application.ports import AssistSuggestion
from application.service import RecoveryService
from domain.models import Channel, OutboundRequest, Requester, ThreadState, UnreturnedItem, Verdict
from domain.reading import CONFIDENT, ground_suggestion
from infrastructure.aws_clients import make_client

NOON = datetime(2026, 10, 22, 12, 0)
TODAY = NOON.date()
ITEM = UnreturnedItem("L-1", "c1", "camera", 3, date(2026, 10, 15))


# ---------- domain: grounding ----------

def test_g13_number_word_in_text_grounds_quantity():
    r = ground_suggestion("I'll bring back the three cameras next week", TODAY, 3, TODAY + timedelta(days=7), 3)
    assert r.quantity == 3 and r.confidence >= CONFIDENT and r.source == "assist"


def test_g13_korean_counter_grounds_quantity():
    r = ground_suggestion("다음 주 화요일에 세 개 갖다 드릴게요", TODAY, 3, TODAY + timedelta(days=5), 3)
    assert r.quantity == 3 and r.confidence >= CONFIDENT


def test_g13_all_of_them_grounds_to_ledger_quantity():
    r = ground_suggestion("we'll drop all of them off friday", TODAY, None, TODAY + timedelta(days=1), 3,
                          all_units=True)
    assert r.quantity == 3 and r.confidence >= CONFIDENT


def test_g13_invented_quantity_is_rejected():
    r = ground_suggestion("will return them soon, sorry", TODAY, 3, TODAY + timedelta(days=2), 3)
    assert r.quantity is None and r.confidence < CONFIDENT


def test_g13_date_outside_window_is_rejected():
    past = ground_suggestion("returning the three units", TODAY, 3, TODAY - timedelta(days=1), 3)
    far = ground_suggestion("returning the three units", TODAY, 3, TODAY + timedelta(days=90), 3)
    assert past.return_date is None and far.return_date is None
    assert past.confidence < CONFIDENT and far.confidence < CONFIDENT


# ---------- application: when it is called, what it may change ----------

class FakeAssistant:
    def __init__(self, suggestion=None, error=None):
        self.suggestion, self.error, self.calls = suggestion, error, []

    def suggest(self, text, today):
        self.calls.append(text)
        if self.error:
            raise self.error
        return self.suggestion


def build(assistant, now=NOON):
    ledger = InMemoryLedger([ITEM], {"c1": {Channel.EMAIL: "c1@example.test", Channel.SMS: "+10000000001"}})
    reg = InMemoryRegistry({"c1": {Channel.EMAIL, Channel.SMS}})
    email, sms = FakeSender(Channel.EMAIL), FakeSender(Channel.SMS)
    svc = RecoveryService(ledger, reg, {Channel.EMAIL: email, Channel.SMS: sms}, FixedClock(now),
                          assistant=assistant)
    t = svc.open_recovery("L-1")
    svc.request_send(t, OutboundRequest(Channel.EMAIL, "c1@example.test", "Please confirm the return.",
                                        Requester.HUMAN))
    return svc, reg, email, t


def kinds(reg):
    return [e["kind"] for e in reg.entries()]


def test_g13_confident_regex_reading_never_calls_the_model():
    fa = FakeAssistant(AssistSuggestion(3, TODAY + timedelta(days=1), None, "fake"))
    svc, reg, _, t = build(fa)
    res = svc.handle_reply(t, "I will bring 3 back tomorrow")
    assert fa.calls == [] and res.proposed_posting is not None and "ASSIST" not in kinds(reg)


def test_g13_low_confidence_reply_grounded_suggestion_proposes_posting():
    fa = FakeAssistant(AssistSuggestion(3, TODAY + timedelta(days=2), None, "fake"))
    svc, reg, _, t = build(fa)
    res = svc.handle_reply(t, "the three cameras will be back on saturday morning")
    assert len(fa.calls) == 1 and res.reading.source == "assist"
    assert res.proposed_posting is not None and res.proposed_posting.quantity == 3
    assert "ASSIST" in kinds(reg) and t.state is ThreadState.WAITING  # posting still needs the human confirm


def test_g13_invented_quantity_hands_off():
    fa = FakeAssistant(AssistSuggestion(3, TODAY + timedelta(days=2), None, "fake"))
    svc, _, _, t = build(fa)
    res = svc.handle_reply(t, "sorry, will return them soon")
    assert res.proposed_posting is None and t.state is ThreadState.HANDOFF


def test_g13_assist_failure_is_logged_and_hands_off():
    svc, reg, _, t = build(FakeAssistant(error=RuntimeError("AccessDeniedException")))
    res = svc.handle_reply(t, "soon")
    assert res.proposed_posting is None and t.handoff_reason == "low_confidence"
    assert "ASSIST_FAILED" in kinds(reg)


def test_g13_follow_up_draft_passes_gate_as_agent():
    fa = FakeAssistant(AssistSuggestion(None, None, "Which day can you bring the cameras back?", "fake"))
    svc, reg, email, t = build(fa)
    res = svc.handle_reply(t, "soon")
    assert res.follow_up is not None and res.follow_up.verdict.verdict is Verdict.PASS
    assert email.calls[-1].requested_by is Requester.AGENT and len(email.calls) == 2
    assert t.state is ThreadState.WAITING


def test_g13_follow_up_with_amount_waits_for_human_approval():
    fa = FakeAssistant(AssistSuggestion(None, None, "You still owe $1,200. When will you return them?", "fake"))
    svc, _, email, t = build(fa)
    res = svc.handle_reply(t, "soon")
    assert res.follow_up.verdict.verdict is Verdict.APPROVAL and len(email.calls) == 1


def test_g13_follow_up_over_daily_cap_is_blocked_and_hands_off():
    fa = FakeAssistant(AssistSuggestion(None, None, "Which day works for the return?", "fake"))
    svc, _, email, t = build(fa)
    svc.request_send(t, OutboundRequest(Channel.EMAIL, "c1@example.test", "Reminder.", Requester.HUMAN))
    res = svc.handle_reply(t, "soon")
    assert res.follow_up.verdict.reason == "daily_cap" and len(email.calls) == 2
    assert t.state is ThreadState.HANDOFF


# ---------- adapter: Bedrock Converse request and parsing ----------

class StubRuntime:
    def __init__(self, text):
        self.text, self.calls = text, []

    def converse(self, **kw):
        self.calls.append(kw)
        return {"output": {"message": {"role": "assistant", "content": [{"text": self.text}]}},
                "usage": {"inputTokens": 180, "outputTokens": 30, "totalTokens": 210}, "stopReason": "end_turn"}


def test_g13_bedrock_request_is_small_deterministic_and_keeps_reply_as_data():
    rt = StubRuntime(json.dumps({"quantity": 3, "all_units": False, "return_date": "2026-10-24", "follow_up": None}))
    a = BedrockReplyAssistant(rt, "amazon.nova-micro-v1:0")
    s = a.suggest("the three cameras on saturday", TODAY)
    kw = rt.calls[0]
    assert kw["modelId"] == "amazon.nova-micro-v1:0"
    assert kw["inferenceConfig"]["temperature"] == 0 and kw["inferenceConfig"]["maxTokens"] <= 200
    assert "the three cameras on saturday" in kw["messages"][0]["content"][0]["text"]
    assert "data" in kw["system"][0]["text"].lower()
    assert s == AssistSuggestion(3, date(2026, 10, 24), None, "amazon.nova-micro-v1:0", False)
    assert a.last_usage == {"inputTokens": 180, "outputTokens": 30, "totalTokens": 210}


def test_g13_bedrock_fenced_json_is_parsed():
    rt = StubRuntime('```json\n{"quantity": null, "all_units": true, "return_date": null, '
                     '"follow_up": "Which day?"}\n```')
    s = BedrockReplyAssistant(rt, "m").suggest("all of them", TODAY)
    assert s.all_units and s.follow_up == "Which day?" and s.quantity is None


def test_g13_bedrock_non_json_raises():
    with pytest.raises(AssistError):
        BedrockReplyAssistant(StubRuntime("Sure! The customer says three."), "m").suggest("x", TODAY)


def test_g13_bedrock_bad_types_raise():
    with pytest.raises(AssistError):
        BedrockReplyAssistant(StubRuntime('{"quantity": "three", "return_date": "next week"}'), "m").suggest("x", TODAY)


def test_g13_client_factory_maps_bedrock_runtime():
    class B:
        def client(self, name, region_name):
            return (name, region_name)
    assert make_client("bedrock", "us-east-1", B()) == ("bedrock-runtime", "us-east-1")


# ---------- G13: weekday word in the customer's text must agree with the date that is posted ----------

from domain.reading import weekday_conflict  # noqa: E402


def test_g13_weekday_word_names_the_day_of_the_date():
    sat, fri = date(2026, 10, 31), date(2026, 10, 30)
    assert weekday_conflict("back on saturday morning", fri) is True
    assert weekday_conflict("back on saturday morning", sat) is False
    assert weekday_conflict("back on Sat", fri) is True and weekday_conflict("see you mon.", date(2026, 11, 2)) is False
    assert weekday_conflict("friday or saturday", fri) is False  # any named day may match
    assert weekday_conflict("3 cameras tomorrow", fri) is False  # no weekday word: nothing to check
    assert weekday_conflict("saturday", None) is False


def test_g13_model_date_with_wrong_weekday_is_handed_off_not_posted():
    monday = datetime(2026, 10, 26, 12, 0)  # saturday is Oct 31; the model says Oct 30 (a Friday)
    fa = FakeAssistant(AssistSuggestion(3, date(2026, 10, 30), "Which day?", "fake"))
    svc, reg, email, t = build(fa, now=monday)
    res = svc.handle_reply(t, "the three cameras will be back on saturday morning")
    assert res.proposed_posting is None and t.state is ThreadState.HANDOFF
    assert t.handoff_reason == "weekday_mismatch" and res.comparison.reason == "weekday_mismatch"
    assert len(email.calls) == 1  # no follow-up sent either: a person decides
    assert any(e["kind"] == "READ" and e["reason"] == "weekday_mismatch" for e in reg.entries())  # not silent


def test_g13_model_date_with_matching_weekday_still_proposes_posting():
    monday = datetime(2026, 10, 26, 12, 0)
    fa = FakeAssistant(AssistSuggestion(3, date(2026, 10, 31), None, "fake"))
    svc, _, _, t = build(fa, now=monday)
    res = svc.handle_reply(t, "the three cameras will be back on saturday morning")
    assert res.proposed_posting is not None and res.proposed_posting.return_date == date(2026, 10, 31)


def test_g13_regex_reader_iso_date_with_wrong_weekday_is_handed_off():
    svc, _, _, t = build(None)
    res = svc.handle_reply(t, "I will bring 3 back on Friday 2026-10-31")  # Oct 31 2026 is a Saturday
    assert res.proposed_posting is None and t.handoff_reason == "weekday_mismatch"
