"""Outbound gate: one pure function, four verdicts. Priority is the order of checks."""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, time, timedelta

from .models import GateVerdict, OutboundRequest, Verdict

DAILY_CAP = 2
QUIET_START = time(21, 0)
QUIET_END = time(8, 0)

_AMOUNT = re.compile(r"[$₩]\s?\d{1,3}(,\d{3})+|[$₩]\s?\d{4,}|\b\d{3,}(,\d{3})*\s?(USD|KRW|dollars|won)\b|\d+\s?만\s?원", re.I)
_SENSITIVE = re.compile(r"legal action|lawyer|collections|court|small claims|법적|소송|채권", re.I)


@dataclass(frozen=True)
class GateContext:
    now_local: datetime
    sent_today: int
    opted_out: bool
    consented: bool
    address_blocked: bool
    human_approved: bool = False


def needs_approval(text: str) -> bool:
    return bool(_AMOUNT.search(text) or _SENSITIVE.search(text))


def in_quiet_hours(now: datetime) -> bool:
    t = now.time()
    return t >= QUIET_START or t < QUIET_END


def next_release(now: datetime) -> datetime:
    day = now.date() if now.time() < QUIET_END else now.date() + timedelta(days=1)
    return datetime.combine(day, QUIET_END)


def evaluate(req: OutboundRequest, ctx: GateContext) -> GateVerdict:
    def v(verdict: Verdict, reason: str, release=None) -> GateVerdict:
        return GateVerdict(verdict, reason, req.channel, req.requested_by, release)

    if ctx.opted_out:
        return v(Verdict.BLOCK, "opt_out")
    if not ctx.consented:
        return v(Verdict.BLOCK, "no_consent")
    if ctx.address_blocked:
        return v(Verdict.BLOCK, "address_blocked")
    if ctx.sent_today >= DAILY_CAP:
        return v(Verdict.BLOCK, "daily_cap")
    if in_quiet_hours(ctx.now_local):
        return v(Verdict.HOLD, "quiet_hours", next_release(ctx.now_local))
    if needs_approval(req.text) and not ctx.human_approved:
        return v(Verdict.APPROVAL, "needs_approval")
    return v(Verdict.PASS, "ok")
