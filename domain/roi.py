"""S7 ROI: money this product changes, per month. Pure arithmetic; every input is a named assumption or a measurement.

saving = overdue_per_month * close_rate * minutes_saved_per_close / 60 * hourly_wage
         - overdue_per_month * sends_per_thread * cost_per_send
Only auto-closed threads save staff time; hand-offs save nothing. When nothing closes the result is the send cost (< 0).
"""
from __future__ import annotations

from dataclasses import dataclass

MIN_WAGE_KRW_2026 = 10320          # Minimum Wage Commission of Korea, 2026 hourly rate (minimumwage.go.kr)
SES_KRW_PER_EMAIL = 0.10 / 1000 * 1364.77   # SES outbound $0.10 per 1,000 emails (aws.amazon.com/ses/pricing); FX assumption
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
