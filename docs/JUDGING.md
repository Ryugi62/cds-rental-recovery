# Judging criteria to evidence

Criteria quoted from the Official Rules, section 6 (aws-cds-partner.devpost.com/rules, read 2026-10-22).

| Criterion (weight) | Rule text | Where to look | Status |
|---|---|---|---|
| Technical Execution (40%) | "Are there multiple AWS CDS services utilized, and well integrated into broader AWS services, specific AI services?" "Is it reproducible?" | SES and SMS sends live (`docs/live/`, screens `docs/screens/aws-*.png`), End User Messaging SMS adapters (`adapters/eum_sms.py`, `adapters/sms_metrics.py`), SNS + Lambda in `template.yaml`, one-line deploy in `AGENTS.md`, 4-layer architecture with a no-reverse-import test (`tests/test_layers.py`) | SES live (2026-10-26); End User Messaging SMS live from a simulator number with delivery, failure and opt-out read back (2026-10-27, `docs/live/sms-log.jsonl`); Lambda `events_handler` deployed directly and invoked (`docs/live/deploy-log.jsonl`); CloudFormation and SNS refused by IAM, logged; Bedrock reply assist live, 3 Converse calls (2026-10-27, `docs/live/bedrock-log.jsonl`); AgentCore planned |
| Potential Value / Impact (20%) | value to customers | `docs/ROI.md` (formula, symbol table, low case below zero), `docs/OFFERING.md` | Formula measured on synthetic replies only |
| Demo Presentation (20%) | "Does it include the end-to-end workflow?" | Gate screen, 11 steps from overdue item to ledger row (`docs/screens/`), local demo in one command | 3-minute demo video: https://youtu.be/SdrfvsAKtew |
| Creativity (10%) | not a copy of a sample | README "How this differs" table (3 AWS samples, 3 products) | |
| Functionality (10%) | works as described | README test count (`tools/check_readme.py` fails if it drifts), `docs/FAILURES.md` (13 failure types, each with a test), live SES log | |

## Prize tracks

| Track | Requirement (rules section 8) | This project |
|---|---|---|
| Overall 1st to 3rd | any eligible submission | entered |
| Best WhatsApp Solution (Meta) | uses End User Messaging Social (WhatsApp) | not entered: no WhatsApp channel |

Rules: "A project can only win one (1) Prize", so there is no second track to stack; the overall track is the only one.
