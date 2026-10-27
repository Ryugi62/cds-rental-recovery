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

## US row: the market where two-way SMS works

The customer scene (text, reply, read, ledger) runs where End User Messaging supports two-way SMS (United States, Canada, United Kingdom, Australia); South Korea is email only. So the headline value uses a US wage. Same formula, same N, c, m, s; only w and p change.

| Symbol | Meaning | Low | Base | High | Source |
|---|---|---|---|---|---|
| w | hourly wage, USD | 7.25 | 7.25 | 7.25 | US federal minimum wage, $7.25 per hour effective July 24, 2009, U.S. Department of Labor, Wage and Hour Division (https://www.dol.gov/agencies/whd/minimum-wage, read 2026-10-27) — a floor, real wages are higher |
| p | cost per email, USD | 0.0001 | 0.0001 | 0.0001 | SES outbound $0.10 per 1,000 emails (aws.amazon.com/ses/pricing, read 2026-10-26) |

One closed thread saves 6 / 60 × 7.25 = **$0.725** of staff time (about 73 cents). Result for N = 40 (computed by `domain/roi.py` `us_scenarios`, checked by `tests/test_roi.py`):

| Scenario | USD per month |
|---|---|
| Low (nothing closes) | <!--roi-us:low-->-0.01<!--/roi--> |
| Base | <!--roi-us:base-->16.56<!--/roi--> |
| High | <!--roi-us:high-->58.00<!--/roi--> |

Size of the lower bound: the most an unclosed thread can cost is its AWS send cost, because the shop pays this product no fee for it. 2 emails = $0.0002. 2 text messages = $0.0239 (the upper price per text, $0.00774 + $0.00421 carrier fee = $0.01195, AWS pricing page, `docs/live/cost-check.md`; the measured spend was $0.00774 each). One closed thread ($0.725) covers the send cost of 30 unclosed text threads, or 3,625 unclosed email threads. No new assumption was added: m = 6 and s = 2 are the rows above.
The Korean figure stays in the first table (email only, 1,032 KRW per closed thread at 10,320 KRW).
