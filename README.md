# cds-rental-recovery

Equipment-rental recovery over text and email, with an outbound gate in front of every send.
Stage 2 of the AWS CDS Agentic AI Partner Hackathon build: domain, application, fake adapters, gate screen.
All data is synthetic. No AWS call is made anywhere in this stage.

## Run

```
python3 -m venv .venv && .venv/bin/pip install pytest boto3
.venv/bin/pytest -q && .venv/bin/python tools/check_readme.py
.venv/bin/python -m infrastructure.web   # open http://127.0.0.1:8765
```

Tests: <!--tests-->76<!--/tests--> passing (`tools/check_readme.py` fails if this number drifts).

## Layers (no reverse imports, enforced by `tests/test_layers.py`)

`domain/` gate policies, reply reading, thread states, event decisions. `application/` use cases and ports.
`adapters/` SES send/inbound/events, End User Messaging SMS, in-memory fakes. `infrastructure/` boto3 client factory (no calls), demo story, web screen.

## Gate screen

Eleven steps: text, bounce, held email, approval, delivery, agent nudge, daily-cap block, reply reading, ledger row.
A second case shows opt-out. Screens at 390px are in `docs/screens/` (`python tools/capture.py` regenerates them and checks for horizontal scroll and text under 16px).

## Not done yet

Real SES and End User Messaging round trip, IaC, AgentCore agent. See SPEC.md S1, S3, S5.
