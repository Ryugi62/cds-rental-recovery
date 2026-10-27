"""S7 ROI: money this product changes, per month. Pure arithmetic; every input is a named assumption or a measurement.

saving = overdue_per_month * close_rate * minutes_saved_per_close / 60 * hourly_wage
         - overdue_per_month * sends_per_thread * cost_per_send
Only auto-closed threads save staff time; hand-offs save nothing. When nothing closes the result is the send cost (< 0).
"""
from __future__ import annotations

from dataclasses import dataclass

MIN_WAGE_KRW_2026 = 10320          # Minimum Wage Commission of Korea, 2026 hourly rate (minimumwage.go.kr)
SES_KRW_PER_EMAIL = 0.10 / 1000 * 1364.77   # SES outbound $0.10 per 1,000 emails (aws.amazon.com/ses/pricing); FX assumption
MIN_WAGE_USD_US_FEDERAL = 7.25     # US Department of Labor, federal minimum wage since 2009-07-24 (dol.gov/agencies/whd/minimum-wage, read 2026-10-27)
SES_USD_PER_EMAIL = 0.10 / 1000    # SES outbound $0.10 per 1,000 emails (aws.amazon.com/ses/pricing)
EUM_USD_PER_SMS_MAX = 0.00774 + 0.00421  # US long code $0.00774 + carrier fee $0.00421, AWS pricing page (docs/live/cost-check.md): the upper price per text
MEASURED_CLOSE_RATE = 8 / 14       # infrastructure/variant_eval.py, 14 synthetic replies, labels written before the run


@dataclass(frozen=True)
class RoiInputs:
    overdue_per_month: int
    close_rate: float
    minutes_saved_per_close: float
    hourly_wage: float
    sends_per_thread: float
    cost_per_send: float


def monthly_saving(inp: RoiInputs) -> float:
    if not 0.0 <= inp.close_rate <= 1.0:
        raise ValueError("close_rate must be within 0..1")
    if inp.overdue_per_month < 0 or inp.minutes_saved_per_close < 0 or inp.sends_per_thread < 0:
        raise ValueError("counts must be non-negative")
    time_value = inp.overdue_per_month * inp.close_rate * inp.minutes_saved_per_close / 60 * inp.hourly_wage
    return time_value - inp.overdue_per_month * inp.sends_per_thread * inp.cost_per_send


def scenarios(overdue_per_month: int, detail: bool = False) -> dict:
    inputs = {
        "low": RoiInputs(overdue_per_month, 0.0, 0, MIN_WAGE_KRW_2026, 2, SES_KRW_PER_EMAIL),
        "base": RoiInputs(overdue_per_month, MEASURED_CLOSE_RATE, 6, MIN_WAGE_KRW_2026, 2, SES_KRW_PER_EMAIL),
        "high": RoiInputs(overdue_per_month, 1.0, 12, MIN_WAGE_KRW_2026, 1, SES_KRW_PER_EMAIL),
    }
    out = {k: monthly_saving(v) for k, v in inputs.items()}
    if detail:
        out["inputs"] = inputs
    return out


def us_closed_thread_value_usd(minutes: float = 6, hourly_wage: float = MIN_WAGE_USD_US_FEDERAL) -> float:
    """Staff time one auto-closed thread saves in a two-way SMS market (US), same m and w roles as the formula above."""
    return minutes / 60 * hourly_wage


def us_scenarios(overdue_per_month: int) -> dict:
    """Same three scenarios as `scenarios`, in USD at the US federal minimum wage and the SES per-email price."""
    return {
        "low": monthly_saving(RoiInputs(overdue_per_month, 0.0, 0, MIN_WAGE_USD_US_FEDERAL, 2, SES_USD_PER_EMAIL)),
        "base": monthly_saving(RoiInputs(overdue_per_month, MEASURED_CLOSE_RATE, 6, MIN_WAGE_USD_US_FEDERAL, 2, SES_USD_PER_EMAIL)),
        "high": monthly_saving(RoiInputs(overdue_per_month, 1.0, 12, MIN_WAGE_USD_US_FEDERAL, 1, SES_USD_PER_EMAIL)),
    }


def unclosed_thread_max_loss_usd(sends: int = 2, per_send_usd: float = SES_USD_PER_EMAIL) -> float:
    """An unclosed thread costs at most its AWS send cost (the shop pays no fee for it)."""
    return sends * per_send_usd


def closed_threads_to_break_even(unclosed_loss_usd: float) -> float:
    """How many unclosed threads one closed thread's saving covers."""
    return us_closed_thread_value_usd() / unclosed_loss_usd
