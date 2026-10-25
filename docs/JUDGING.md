# Judging criteria to evidence

Criteria quoted from the Official Rules, section 6 (aws-cds-partner.devpost.com/rules, read 2026-10-22).

| Criterion (weight) | Rule text | Where to look | Status |
|---|---|---|---|
| Technical Execution (40%) | "Are there multiple AWS CDS services utilized, and well integrated into broader AWS services, specific AI services?" "Is it reproducible?" | SES send live (`docs/live/`), End User Messaging SMS adapter (`adapters/eum_sms.py`), SNS + Lambda in `template.yaml`, one-line deploy in `AGENTS.md`, 4-layer architecture with a no-reverse-import test (`tests/test_layers.py`) | SES live; SMS, SNS, Lambda code and tests only; AgentCore planned |
| Potential Value / Impact (20%) | value to customers | `docs/ROI.md` (formula, symbol table, low case below zero), `docs/OFFERING.md` | Formula measured on synthetic replies only |
| Demo Presentation (20%) | "Does it include the end-to-end workflow?" | Gate screen, 11 steps from overdue item to ledger row (`docs/screens/`), local demo in one command | Video not yet recorded |
| Creativity (10%) | not a copy of a sample | README "How this differs" table (3 AWS samples, 3 products) | |
| Functionality (10%) | works as described | README test count (`tools/check_readme.py` fails if it drifts), `docs/FAILURES.md` (11 failure types, each with a test), live SES log | |
