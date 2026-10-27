# Rental Recovery: two AWS CDS services, Amazon SES and End User Messaging SMS, run live in an agentic workflow that stops before it over-sends

Small rental shops chase overdue equipment by hand, and an AI agent that helps can over-send. Here, every message, from a person or an agent, goes through one gate first; a thread that closes by customer reply and matches the ledger saves about $0.73 of staff time (assumed 6 minutes at the US federal minimum wage of $7.25, [dol.gov](https://www.dol.gov/agencies/whd/minimum-wage), read 2026-10-27; South Korea is email only, own figure in [docs/ROI.md](docs/ROI.md)). The shop pays $0.25 per closed thread; threads handed to a person cost no fee. The lower bound is shown, not hidden: an unclosed thread costs at most its AWS send cost ($0.0002 for 2 emails, $0.024 for 2 texts), and one closed thread covers 30 unclosed text threads. AWS usage is billed to the shop's own account.

A small equipment-rental shop chases every overdue item by hand: a text or email asking "when will you bring it back?", then a ledger update. This repo runs that conversation end to end on AWS Communication Developer Services (Amazon SES and End User Messaging SMS): open the overdue item, send through an outbound gate (PASS, HOLD, BLOCK or APPROVAL, shown before every send, human or agent), read the reply into quantity and date, check it against the ledger, then post it and close, or hand it to a person with a reason. Delivery, bounce and opt-out events change the next decision.

**What is different:** an AI agent's proposal cannot get around the gate either (one dispatch point, test `test_g11_no_path_to_sender_except_gate`), and the customer's answer is checked against the ledger before anything is posted. The customer scene is a market where two-way SMS is supported (United States, Canada, United Kingdom, Australia in the End User Messaging country table); in South Korea two-way SMS is not supported, so there the conversation runs on email only.

**Try it in 3 minutes, no AWS account, no login, no install:** `python3 -m infrastructure.web` then open http://127.0.0.1:8765 (Python 3.9+, standard library only). At step 10 type your own customer reply; the reader and ledger check run on your text. All data on the screen is synthetic. Example: "We will drop off all 3 on Thursday morning" reads as 3 units, Oct 29, matches the ledger ([screenshot](docs/screens/try-your-reply.png), fresh browser, no login).

## How this differs from what already exists

Read from each product's public page on 2026-10-26. "Not shown" means we did not see it there, not that it cannot be done.

| Product | What it does for this job | What we add |
|---|---|---|
| [AWS sample: AI campaign orchestrator](https://github.com/aws-samples/sample-ai-campaign-orchestrator) (Bedrock + End User Messaging) | Picks a channel per customer, holds sends to fatigued or unhappy customers (count over a window, sentiment threshold) | A per-message verdict with four policies (opt-out, quiet hours, daily cap, approval) on a one-to-one conversation, and the reply read back into a ledger |
| [AWS sample: SES Mail Manager attachment pipeline](https://github.com/aws-samples/sample-amazon-ses-mail-manager-attachment-pipeline) | Inbound email classified by Bedrock; machine-readable deployment guide for agents | The outbound side and the loop: send, event, reply, ledger post or hand-off; our own agent guide in [AGENTS.md](AGENTS.md) |
| [AWS sample: RCS agent setup](https://github.com/aws-samples/sample-rcs-agent-setup-and-send-messages) | AGENTS.md skills that set up an RCS agent and send messages | A business conversation that ends in a state change (CLOSED or HANDOFF), not channel setup |
| [Booqable](https://booqable.com/features/) (rental software) | Marks late returns in a dashboard; email reminder templates | Not shown: reading the customer's answer and checking it against the ledger |
| [EZRentOut](https://www.ezrentout.com/) (rental software) | One view of what is out, due back or overdue | Not shown: two-way messaging with a send gate |
| [Chaser](https://www.chaserhq.com/) (invoice chasing) | Email and SMS payment reminders, AI email generator | Built for invoices, not equipment returns; not shown: event-driven stop after bounce or opt-out |
| [SES account-level suppression list](https://docs.aws.amazon.com/ses/latest/dg/sending-email-suppression-list.html) and [SMS opt-out list](https://docs.aws.amazon.com/sms-voice/latest/userguide/opt-out-list.html) (built into AWS) | SES: hard bounces and complaints are listed; a send to a listed address is accepted but not delivered, and still counts toward the daily sending quota. SMS: a number that replies STOP is listed and later messages to it are not sent | We keep both on as the last line. The gate decides earlier and on more: quiet hours, daily cap and approval for amounts or legal words, before the provider is called (0 calls, 0 quota), and the event moves the conversation itself (switch channel or hand off to a person), not only the address |

**Only here:** every send, including one an AI agent proposes or a model drafts, shows its gate verdict before it leaves, and SES/SMS events and the customer's reply change the next decision instead of a fixed reminder schedule.

## What is real and what is simulated

| Part | Status | Evidence |
|---|---|---|
| SES sends through the gate (<!--live:ses_sends=4-->4 first sends and <!--live:ses_retries=2-->2 retried sends that passed) and DELIVERY, BOUNCE, OPT_OUT events read back | Real, us-east-1 sandbox, mailbox simulator and owner inbox only | `docs/live/live-log.jsonl`, `docs/live/EXCERPT.md` |
| Customer reply read into quantity and date, posted, thread CLOSED | Reading is real; the reply travelled by the owner's Gmail, not SES receiving | live-log lines 18-19 |
| End User Messaging SMS sends through the gate, and the result read back | Real, us-east-1 SMS sandbox, AWS simulator numbers only (the traffic stays inside AWS, no phone receives it): <!--live:sms_sends=3-->3 sends PASS from a simulator origination number; delivery read back from CloudWatch `AWS/SMSVoice` (DELIVERY), the failure number not delivered (BOUNCE, retry BLOCK with 0 SMS calls), the account opt-out list read back (OPT_OUT, retry BLOCK with 0 SMS calls). Events come from CloudWatch counts, one send per minute, because the IAM user may not create an SNS event destination | `docs/live/sms-log.jsonl`, `tools/live_sms.py`, `adapters/sms_metrics.py`, `docs/screens/aws-sms-live.png` |
| Lambda `events_handler` | Deployed without CloudFormation (`tools/deploy_direct.py`); it borrowed an existing log-only execution role because the IAM user may not create roles (the role name is visible on the screen, not hidden). Invoked 3 times: SMS delivery shape carrying the real SMS message id, SES bounce, and an unknown type that comes back `ignored: 1`. The invocations used documented event shapes; AWS did not push them, because SNS is denied to the IAM user | `docs/live/deploy-log.jsonl`, `docs/screens/aws-lambda-deploy.png` |
| SES receiving, SNS topics, inbound Lambda (`template.yaml`) | Code, unit tests, `cfn-lint` pass; not deployed. SES receiving needs a domain with an MX record, which this account does not own; SNS `CreateTopic` is refused by IAM | `tests/test_lambda_handlers.py`, [AGENTS.md](AGENTS.md) |
| AI agent | A scripted agent stands in for AgentCore; it goes through the same gate | `test_g11_no_path_to_sender_except_gate` |
| Reply-reading assist on Amazon Bedrock (Converse, Nova Micro), called only when the regex reader's confidence is below 0.8 | Code and 21 tests (fake client). Live: <!--live:bedrock_calls=6-->6 Converse calls succeeded on 2026-10-27 in two runs of 3 (about $0.00007 in all; the first run was before the weekday check, the second after). Second run, same 3 replies: "saturday" came back as Oct 30 (a Friday) and "friday" as Oct 31 (a Saturday); the weekday check refused both (`weekday_mismatch`), nothing was posted and both went to a person. The third reply stayed unread and nothing was guessed. First run, kept in the log: the Saturday reply was posted as a match for Oct 30, which is the case the check now stops. An attempt on 2026-10-26 was refused by IAM (`AccessDeniedException`) and ended in logged hand-offs | `adapters/bedrock.py`, `domain/reading.py`, `tests/test_reply_assist.py`, `docs/live/bedrock-log.jsonl`, `docs/screens/aws-bedrock.png` |
| Closure rate 8 of 14 reply variants | Measures the gate and hand-off rules, not language understanding (regex reader, synthetic replies) | `infrastructure/variant_eval.py` |
| Deployment (`template.yaml`) | CloudFormation `CreateStack` refused by IAM on 2026-10-27 (logged). The parts the IAM user may create were deployed directly: Lambda `cds-rr-events`, SMS configuration set `cds-rr-sms`; SES configuration set `cds-rr` exists from the SES run | `docs/live/deploy-log.jsonl` |
| Screen | Synthetic data, labelled on every screen | `docs/screens/` |

A partner sells it per shop: install with `sam deploy` into the shop's own AWS account (the five steps in [docs/OFFERING.md](docs/OFFERING.md)), the shop pays $0.25 per closed thread and nothing for a thread handed to a person.

Value is stated as a formula with its lower bound: `N × c × m / 60 × w − N × s × p` ([docs/ROI.md](docs/ROI.md)); base case 23,578 KRW (about $17) per month for 40 overdue items at the Korean minimum wage, or $16.56 at the US federal minimum wage (US row in the same file); low case below zero by the send cost only ($0.008 for 40 threads).

![Architecture](docs/architecture.png)

## Scaling

What limits it today, measured: the ledger is in memory (the demo and the live runs load it from code, nothing is stored between runs); events are read back from CloudWatch counts, which limits the live SMS run to one send per minute (`tools/live_sms.py`); the SES sandbox allows 200 emails per 24 hours and 1 per second (`get_account`). The design that replaces the polling is in `template.yaml`: SES and SMS events go to an SNS topic and are pushed into the `events_handler` Lambda, so there is no per-minute read and no polling loop. That path is unit-tested but not deployed here (SNS `CreateTopic` is refused by this account's IAM). A stored ledger is not built; it is listed under Not done yet.

## Gate verdicts on screen (390 px)

| PASS | HOLD | APPROVAL | BLOCK |
|---|---|---|---|
| ![PASS](docs/screens/main-01.png) | ![HOLD](docs/screens/main-03.png) | ![APPROVAL](docs/screens/main-04.png) | ![BLOCK](docs/screens/main-08.png) |

Failure handling, one row per failure type with its test: [docs/FAILURES.md](docs/FAILURES.md). Judging criteria to evidence: [docs/JUDGING.md](docs/JUDGING.md). Offering and pricing: [docs/OFFERING.md](docs/OFFERING.md). Sources for every AWS fact quoted here: [docs/SOURCES.md](docs/SOURCES.md).

## Run

```
python3 -m venv .venv && .venv/bin/pip install pytest boto3
.venv/bin/pytest -q && .venv/bin/python tools/check_readme.py
.venv/bin/python -m infrastructure.web   # open http://127.0.0.1:8765
```

Tests: <!--tests-->143<!--/tests--> passing (`tools/check_readme.py` fails if this number drifts).

## AWS reproduction

Everything above runs locally with no account. To repeat the live runs in your own AWS account (us-east-1, SES and SMS sandboxes; only verified addresses and AWS simulator numbers receive), the IAM user needs these actions. The list is read from the API calls in the code (`grep` for `send_email`, `send_text_message`, `converse`, ...), not from memory:

| Step | Code that calls it | IAM actions |
|---|---|---|
| Send email through the gate | `adapters/ses.py` (`send_email`) | `ses:SendEmail` on a verified identity |
| Read SES events back (no SNS) | `adapters/ses_metrics.py` (`list_metrics`) | `cloudwatch:ListMetrics` |
| Send text, read opt-outs | `adapters/eum_sms.py` (`send_text_message`, `describe_opted_out_numbers`), `tools/live_sms.py` (`describe_phone_numbers`, `put_opted_out_number`) | `sms-voice:SendTextMessage`, `sms-voice:DescribeOptedOutNumbers`, `sms-voice:DescribePhoneNumbers`, `sms-voice:PutOptedOutNumber`; a SIMULATOR origination number must exist first (`sms-voice:RequestPhoneNumber`, requested by hand once, $1 a month) |
| Read SMS delivery back | `adapters/sms_metrics.py` (`get_metric_data`, namespace `AWS/SMSVoice`) | `cloudwatch:GetMetricData` |
| Reply assist | `adapters/bedrock.py` (`converse`) | `bedrock:InvokeModel` on `amazon.nova-micro-v1:0` (model access enabled for the account) |
| Deploy without CloudFormation | `tools/deploy_direct.py` | `sms-voice:DescribeConfigurationSets`, `sms-voice:CreateConfigurationSet`, `iam:GetRole`, `iam:PassRole` (the role you pass), `lambda:GetFunction`, `lambda:CreateFunction`, `lambda:UpdateFunctionCode`, `lambda:InvokeFunction`, `sns:CreateTopic` (optional, skipped and logged when refused) |
| Deploy with CloudFormation | `template.yaml` | the CloudFormation, Lambda, IAM-role, SNS, SES, SMS Voice and S3 actions the stack creates (see [AGENTS.md](AGENTS.md)) |

Deploy with the template (needs the actions in the last row):

```
sam deploy --stack-name cds-rental-recovery --resolve-s3 --capabilities CAPABILITY_IAM --parameter-overrides SenderEmail=<address you own>
```

Without CloudFormation (what the author had to use; no IAM role or policy is created or changed):

```
AWS_PROFILE=<p> CDS_LAMBDA_ROLE=<existing role with AWSLambdaBasicExecutionRole> python3 tools/deploy_direct.py deploy
AWS_PROFILE=<p> python3 tools/deploy_direct.py invoke   # one Lambda invocation per event shape
```

Then the live runs: `AWS_PROFILE=<p> python3 tools/live_ses.py send` then `settle`; `python3 tools/live_sms.py send <case>` then `settle <case>`; `python3 tools/live_bedrock.py`. The errors this account got instead (CloudFormation `CreateStack` and SNS `CreateTopic` refused) are kept unedited in `docs/live/deploy-log.jsonl`.

## Layers (no reverse imports, enforced by `tests/test_layers.py`)

`domain/` gate policies, reply reading, thread states, event decisions. `application/` use cases and ports.
`adapters/` SES send/inbound/events, End User Messaging SMS, Bedrock reply assist, in-memory fakes. `infrastructure/` boto3 client factory (no calls), demo story, web screen.

## Gate screen

Eleven steps: text, bounce, held email, approval, delivery, agent nudge, daily-cap block, reply reading, ledger row.
A second case shows opt-out. Screens at 390px are in `docs/screens/` (`python tools/capture.py` regenerates them and checks for horizontal scroll and text under 16px).

## Live SES run (2026-10-26 KST, us-east-1, sandbox account)

Times in the log are UTC: 2026-10-25 20:01 to 20:04 UTC is 2026-10-26 05:01 to 05:04 KST.

Log: `docs/live/live-log.jsonl` (excerpt `docs/live/EXCERPT.md`). Four gated sends through `RecoveryService` + `SesEmailSender` (all PASS): owner inbox, `success@`, `bounce@`, `complaint@simulator.amazonses.com`.
Events read back from the CloudWatch destination of the SES configuration set, then fed to `handle_event`:

| case | event | decision | same send retried |
|---|---|---|---|
| success@ | DELIVERY | delivered, nudge timer | PASS (SES called) |
| bounce@ | BOUNCE | address blocked, no other channel, hand-off | BLOCK address_blocked, SES calls 0 |
| complaint@ | DELIVERY + OPT_OUT | customer opted out, hand-off | BLOCK opt_out, SES calls 0 |

Limits measured on this account (`get_account`): 200 sends per 24 h, 1 send per second (sandbox); only verified addresses and the simulator can receive. Failure path: BOUNCE and OPT_OUT end in a hand-off item, never a silent retry.

Reply leg: a reply typed into the owner's inbox ("I'll bring back 3 on Thursday") was read back and parsed: qty 3, 2026-10-29, confidence 0.9, matches ledger, posted, thread CLOSED.
Not real: SES did not receive that reply. SES inbound needs a verified domain with an MX record, which this account does not have (buying one is a cost decision). The reply therefore travelled by Gmail, not SES receiving. The send from the owner's own Gmail address to itself was reported Delivered by SES but never appeared in Gmail (forged-sender drop), so the S1 round trip is partial.

## Live SMS run (2026-10-27, us-east-1, SMS sandbox, simulator numbers)

Log: `docs/live/sms-log.jsonl` ([screen](docs/screens/aws-sms-live.png)). Cost checked first from the AWS pricing page (`docs/live/cost-check.md`): simulator number $1 a month, sends at the standard rate; the account's own SMS limit is $1 a month and every call carries `MaxPrice` 0.02.
Each send goes through `RecoveryService` + `EumSmsSender` from a SIMULATOR origination number; the result is read back from CloudWatch `AWS/SMSVoice` (`CloudWatchSmsDelivery`) or from the account opt-out list (`SmsOptOutList`) and fed to `handle_event`:

| case | read back | decision | same send retried |
|---|---|---|---|
| success simulator number | sent 1, delivered 1: DELIVERY | delivered, nudge timer | PASS (SMS sent again) |
| failure simulator number | sent 1, delivered 0 after 10 min: BOUNCE | bounced and no other channel, hand-off | BLOCK address_blocked, SMS calls 0 |
| success number on the opt-out list | OPT_OUT (STOP stand-in: a simulator cannot reply, so the owner listed it) | customer opted out, hand-off | BLOCK opt_out, SMS calls 0 |

Measured spend: 3 SMS at $0.00774 each (the account's `TextMessageMonthlySpend` metric) = about $0.023, plus the simulator number lease of $1.00 a month.

## Reply variants (k = 14, synthetic, `python3 -m infrastructure.variant_eval`)

Same recovery conversation, 14 customer replies (8 clean in English/Korean/ISO/abbreviations, 6 that must go to a human). Labels were written before the run.
Closed 8 of 14 (57%); all 8 expected-closed reached CLOSED; the 6 others handed off at the first reply (hand-off turn 1); auto-closed against the label 0; send after opt-out BLOCK with 0 provider calls; policy violations 0. The reader is regex-based, so this measures the gate and hand-off rules, not language understanding.

## Not done yet

SES receiving on a verified domain (no owned domain), events pushed by SNS into the Lambda (SNS denied to the IAM user; events are read from CloudWatch instead), a CloudFormation deploy (CreateStack denied), SMS to a real phone (the sandbox allows only verified numbers; we used simulator numbers), a stored ledger, an AgentCore agent. The live Bedrock run is `AWS_PROFILE=<p> python3 tools/live_bedrock.py`. See SPEC.md S1, S3, S5, G13.

## Pre-existing work and license

All code in this repo was written from 2026-10-22 (first commit 2026-10-22). No pre-existing code is included. The idea of a send gate comes from the author's earlier private experience of an agent over-sending; no code from it is used. License: MIT ([LICENSE](LICENSE)).
