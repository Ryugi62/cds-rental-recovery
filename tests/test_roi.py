"""S7: ROI formula whose lower bound (nothing closes) is shown, not hidden. Only the part this product changes (auto-closed threads) counts."""
import pytest
from domain.roi import RoiInputs, monthly_saving, scenarios


def test_formula_is_overdue_times_close_rate_times_minutes_times_wage_minus_send_cost():
    inp = RoiInputs(overdue_per_month=40, close_rate=0.5, minutes_saved_per_close=6, hourly_wage=10320,
                    sends_per_thread=2, cost_per_send=0.0)
    assert monthly_saving(inp) == pytest.approx(40 * 0.5 * 6 / 60 * 10320)


def test_send_cost_is_subtracted_for_every_thread_not_only_closed_ones():
    inp = RoiInputs(40, 0.5, 6, 10320, sends_per_thread=2, cost_per_send=1.0)
    assert monthly_saving(inp) == pytest.approx(40 * 0.5 * 6 / 60 * 10320 - 40 * 2 * 1.0)


def test_lower_bound_shows_the_send_cost_when_nothing_closes():
    inp = RoiInputs(40, 0.0, 6, 10320, sends_per_thread=2, cost_per_send=0.14)
    assert monthly_saving(inp) == pytest.approx(-40 * 2 * 0.14)


def test_scenarios_low_base_high_are_ordered_and_low_is_at_most_zero():
    s = scenarios(overdue_per_month=40)
    assert s["low"] <= 0.0 < s["base"] < s["high"]


def test_base_uses_measured_close_rate_8_of_14():
    s = scenarios(overdue_per_month=40, detail=True)
    assert s["inputs"]["base"].close_rate == pytest.approx(8 / 14)


def test_rejects_rates_outside_0_1():
    with pytest.raises(ValueError):
        monthly_saving(RoiInputs(40, 1.2, 6, 10320, 2, 0.0))


def test_roi_doc_numbers_match_the_formula():
    import pathlib, re
    doc = (pathlib.Path(__file__).resolve().parent.parent / "docs" / "ROI.md").read_text()
    shown = {k: int(v.replace(",", "")) for k, v in re.findall(r"<!--roi:(\w+)-->(-?[\d,]+)<!--/roi-->", doc)}
    real = {k: round(v) for k, v in scenarios(overdue_per_month=40).items()}
    assert shown == real
