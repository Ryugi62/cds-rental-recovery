# ROI: only the part this product changes

Problem, as a number: a small rental shop has **N overdue unreturned items per month**; each needs a "when will you bring it back?" check by phone or text and a ledger update by a person.
This product changes one thing: a thread that the reader can close (reply matches the ledger) needs no person. Hand-offs save nothing.

```
monthly saving (KRW) = N × c × m / 60 × w  −  N × s × p
```

| Symbol | Meaning | Low | Base | High | Source |
|---|---|---|---|---|---|
| N | overdue items per month | 40 | 40 | 40 | assumption (no real customer numbers in this repo, SPEC non-goal); scale linearly |
| c | share of threads closed without a person | 0 | 8/14 = 0.571 | 1.0 | base measured: `python3 -m infrastructure.variant_eval`, 14 synthetic replies, labels written before the run |
| m | staff minutes saved per closed thread | 0 | 6 | 12 | assumption (one call or text plus one ledger line) |
| w | hourly wage, KRW | 10,320 | 10,320 | 10,320 | Korea 2026 minimum hourly wage, Minimum Wage Commission (minimumwage.go.kr, read 2026-10-26) — a floor, real wages are higher |
| s | sends per thread | 2 | 2 | 1 | daily cap is 2 (gate policy) |
| p | cost per email, KRW | 0.136 | 0.136 | 0.136 | SES outbound $0.10 per 1,000 emails (aws.amazon.com/ses/pricing, read 2026-10-26) × 1,364.77 KRW/USD (assumption) |

Result for N = 40 (computed by `domain/roi.py`, checked by `tests/test_roi.py`):

| Scenario | KRW per month | USD per month |
|---|---|---|
| Low (nothing closes) | <!--roi:low-->-11<!--/roi--> | -0.01 |
| Base | <!--roi:base-->23,578<!--/roi--> | 17.28 |
| High | <!--roi:high-->82,555<!--/roi--> | 60.49 |

What this does not count: earlier return of equipment (more rental days sold), unpaid balances collected, fewer lost items. None of those is measured yet, so none is claimed.
The low case is negative on purpose: if the reader closes nothing, the shop pays only the send cost and gets the hand-off queue it already had by hand.
