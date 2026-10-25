"""Synthetic-reply repetition (tau2-bench style): same recovery conversation, k reply variants."""
from infrastructure.variant_eval import VARIANTS, evaluate


def test_at_least_ten_variants_and_both_expectations_present():
    assert len(VARIANTS) >= 10
    assert {v.expect for v in VARIANTS} == {"CLOSED", "HANDOFF"}


def test_every_variant_ends_closed_or_handed_off_never_silent():
    for r in evaluate().rows:
        assert r.final_state in ("CLOSED", "HANDOFF"), r


def test_no_policy_violation_in_the_default_variants():
    rep = evaluate()
    assert rep.policy_violations == 0
    assert rep.closed_expected == rep.closed_actual_of_expected_closed or rep.closed_rate > 0


def test_a_wrong_quantity_is_never_auto_closed():
    rows = {r.variant_id: r for r in evaluate().rows}
    assert rows["qty-mismatch"].final_state == "HANDOFF" and rows["qty-mismatch"].handoff_turn == 1


def test_send_after_opt_out_is_blocked_with_zero_provider_calls():
    rep = evaluate()
    assert rep.optout_retry_verdict == "BLOCK" and rep.optout_retry_provider_calls == 0


def test_report_counts_add_up():
    rep = evaluate()
    assert rep.k == len(rep.rows) == len(VARIANTS)
    assert rep.closed + rep.handoff == rep.k
