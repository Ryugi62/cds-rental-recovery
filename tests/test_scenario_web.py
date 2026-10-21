"""Gate screen: the synthetic story and its HTML."""
import re
from domain.models import ThreadState, Verdict
from infrastructure.demo_scenario import build_story, build_optout_story
from infrastructure.web import render_page


def test_story_shows_all_four_verdicts():
    story = build_story()
    shown = {s.verdict.verdict for s in story.steps if s.verdict}
    assert shown == {Verdict.PASS, Verdict.HOLD, Verdict.BLOCK, Verdict.APPROVAL}


def test_story_closes_with_one_ledger_row():
    story = build_story()
    assert story.steps[-1].thread_state is ThreadState.CLOSED
    assert len(story.steps[-1].ledger_rows) == 1


def test_story_has_sms_then_email_and_bounce_switch():
    story = build_story()
    chans = [s.verdict.channel.value for s in story.steps if s.verdict and s.verdict.verdict is Verdict.PASS]
    assert chans[0] == "SMS" and "EMAIL" in chans
    assert any(s.event and s.event.kind.value == "BOUNCE" for s in story.steps)
    assert any(s.event and s.event.kind.value == "DELIVERY" for s in story.steps)


def test_blocked_and_held_steps_never_call_a_sender():
    story = build_story()
    for s in story.steps:
        if s.verdict and s.verdict.verdict in (Verdict.BLOCK, Verdict.HOLD, Verdict.APPROVAL):
            assert s.sender_calls_delta == 0


def test_optout_story_blocks_after_stop():
    story = build_optout_story()
    last = [s for s in story.steps if s.verdict][-1]
    assert last.verdict.verdict is Verdict.BLOCK and last.verdict.reason == "opt_out"
    assert story.steps[-1].thread_state is ThreadState.HANDOFF


def test_page_marks_synthetic_and_has_mobile_viewport():
    story = build_story()
    html = render_page(story, 0)
    assert "Synthetic" in html and 'name="viewport"' in html


def test_every_page_has_exactly_one_primary_action_and_verdict_has_text_and_color():
    story = build_story()
    for i in range(len(story.steps)):
        html = render_page(story, i)
        assert len(re.findall(r'class="primary"', html)) <= 1
    v = next(i for i, s in enumerate(story.steps) if s.verdict and s.verdict.verdict is Verdict.BLOCK)
    html = render_page(story, v)
    assert "BLOCK" in html and "v-block" in html and "daily cap" in html.lower()


def test_reply_step_uses_judge_text():
    story = build_story(reply_text="I will return 2 units tomorrow")
    last_read = [s for s in story.steps if s.reading][-1]
    assert last_read.reading.quantity == 2 and last_read.comparison.reason == "quantity_mismatch"
    assert story.steps[-1].thread_state is ThreadState.HANDOFF
    assert story.steps[-1].ledger_rows == []


def test_page_escapes_user_text():
    story = build_story(reply_text="<script>alert(1)</script> 3 Thursday")
    html = "".join(render_page(story, i) for i in range(len(story.steps)))
    assert "<script>alert" not in html
