# AGENTS.md: deploy and verify cds-rental-recovery

Written for an AI coding assistant (or a person) deploying this repo into their own AWS account. Run the steps in order; stop at the first failure and report it. Do not send to any address you do not own.

## 1. Preflight (no AWS writes)
1. `python3 -m venv .venv && .venv/bin/pip install pytest boto3 cfn-lint`
2. `.venv/bin/pytest -q` must pass; `.venv/bin/python tools/check_readme.py` must print `OK` (README test count = real count).
3. `.venv/bin/cfn-lint template.yaml` must exit 0.
4. Account limits: `aws sesv2 get-account --query '{prod:ProductionAccessEnabled,quota:SendQuota}'`. In the SES sandbox you can send only to verified addresses and the mailbox simulator, 200 per 24 h, 1 per second.
5. Permissions the deploying principal needs: CloudFormation, Lambda, IAM role creation for Lambda, SNS, SES, SMS Voice v2, S3 (for `--resolve-s3`).

## 2. Deploy (one line)
```
sam deploy --stack-name cds-rental-recovery --resolve-s3 --capabilities CAPABILITY_IAM --parameter-overrides SenderEmail=<address you own>
```
Optional SES receiving: add `InboundDomain=<domain with MX to inbound-smtp.<region>.amazonaws.com>`, then once:
`aws ses set-active-receipt-rule-set --rule-set-name <InboundRuleSetName output>` (CloudFormation cannot activate a rule set).

## 3. Post-deploy checks
1. Click the SES verification link sent to `SenderEmail`.
2. Send through the gate to the simulator: `CDS_SENDER=<address> AWS_PROFILE=<profile> python3 tools/live_ses.py send`.
3. Events reach the Lambda: `sam logs -n EventsFunction --stack-name cds-rental-recovery` shows one JSON line per event, e.g. `{"kind": "BOUNCE", ... "block_address": true}` for `bounce@simulator.amazonses.com` and `{"kind": "OPT_OUT", ... "opt_out_customer": true}` for `complaint@simulator.amazonses.com`.
4. Unknown event types appear as `{"kind": "IGNORED", ...}`, never dropped silently (`docs/FAILURES.md`).
5. With `InboundDomain`: reply to the message from your own inbox to `reply@<domain>`; `sam logs -n InboundFunction` shows `quantity`, `return_date`, `confidence`.

## Status of this guide (honest)
- Preflight 1 to 3: run by the author, passing (see README test count).
- Deploy and post-deploy 3 to 5: not yet run by the author. The author's IAM user is denied CloudFormation (`ListStacks`, `ValidateTemplate`: AccessDenied, 2026-10-26), so the template is checked by `cfn-lint` and the handlers by unit tests only. The live sends in `docs/live/` used the same adapters without CloudFormation.
