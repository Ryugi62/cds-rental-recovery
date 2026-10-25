# cds-rental-recovery

Equipment-rental recovery over text and email, with an outbound gate in front of every send.
Stage 2 of the AWS CDS Agentic AI Partner Hackathon build: domain, application, fake adapters, gate screen.
All data is synthetic. Unit tests make no AWS call; `tools/live_ses.py` is the only code that does (owner inbox and SES mailbox simulator only).

## Run

```
python3 -m venv .venv && .venv/bin/pip install pytest boto3
.venv/bin/pytest -q && .venv/bin/python tools/check_readme.py
.venv/bin/python -m infrastructure.web   # open http://127.0.0.1:8765
```

Tests: <!--tests-->88<!--/tests--> passing (`tools/check_readme.py` fails if this number drifts).

## Layers (no reverse imports, enforced by `tests/test_layers.py`)

`domain/` gate policies, reply reading, thread states, event decisions. `application/` use cases and ports.
`adapters/` SES send/inbound/events, End User Messaging SMS, in-memory fakes. `infrastructure/` boto3 client factory (no calls), demo story, web screen.

## Gate screen

Eleven steps: text, bounce, held email, approval, delivery, agent nudge, daily-cap block, reply reading, ledger row.
A second case shows opt-out. Screens at 390px are in `docs/screens/` (`python tools/capture.py` regenerates them and checks for horizontal scroll and text under 16px).

## Live SES run (2026-10-26, us-east-1, sandbox account)

Log: `docs/live/live-log.jsonl` (excerpt `docs/live/EXCERPT.md`). Four gated sends through `RecoveryService` + `SesEmailSender` (all PASS): owner inbox, `success@`, `bounce@`, `complaint@simulator.amazonses.com`.
Events read back from the CloudWatch destination of the SES configuration set, then fed to `handle_event`:

| case | event | decision | same send retried |
|---|---|---|---|
| success@ | DELIVERY | delivered, nudge timer | PASS (SES called) |
| bounce@ | BOUNCE | address blocked, no other channel, hand-off | BLOCK address_blocked, SES calls 0 |
| complaint@ | DELIVERY + OPT_OUT | customer opted out, hand-off | BLOCK opt_out, SES calls 0 |

Reply leg: a reply typed into the owner's inbox ("I'll bring back 3 on Thursday") was read back and parsed: qty 3, 2026-10-29, confidence 0.9, matches ledger, posted, thread CLOSED.
Not real: SES did not receive that reply. SES inbound needs a verified domain with an MX record, which this account does not have (buying one is a cost decision). The reply therefore travelled by Gmail, not SES receiving. The send from the owner's own Gmail address to itself was reported Delivered by SES but never appeared in Gmail (forged-sender drop), so the S1 round trip is partial.

## Reply variants (k = 14, synthetic, `python3 -m infrastructure.variant_eval`)

Same recovery conversation, 14 customer replies (8 clean in English/Korean/ISO/abbreviations, 6 that must go to a human). Labels were written before the run.
Closed 8 of 14 (57%); all 8 expected-closed reached CLOSED; the 6 others handed off at the first reply (hand-off turn 1); auto-closed against the label 0; send after opt-out BLOCK with 0 provider calls; policy violations 0. The reader is regex-based, so this measures the gate and hand-off rules, not language understanding.

## Not done yet

SES inbound (needs a domain), End User Messaging SMS live send, IaC, AgentCore agent. See SPEC.md S1, S3, S5.
