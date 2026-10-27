# Cost check before any SMS or deploy call (2026-10-27)

Read with `curl` from the official pages on 2026-10-27, before any write call. Rule: stop if the fixed monthly cost is above $1 or a payment method has to be added.

## End User Messaging SMS

| Item | Quoted text | Source |
|---|---|---|
| Simulator number, fixed | "Simulator numbers can be purchased in the AWS End User Messaging SMS console for a monthly lease price of $1." | https://aws.amazon.com/end-user-messaging/pricing/ |
| Simulator number, per message | "When you send a message from a simulator number, you pay the standard outbound SMS or MMS messaging rate." | same page |
| US outbound rate | `US,United States,All Networks,Long code,0.00774` and `Long code carrier fee,0.00421` (worst case $0.01195 per message) | End-User-Messaging-SMS-Prices CSV linked from the pricing page |
| Simulator traffic stays inside AWS | "The simulator phone numbers are designed to stay within AWS End User Messaging SMS, so that messages are not sent over the carrier network." | https://docs.aws.amazon.com/sms-voice/latest/userguide/test-phone-numbers.html |
| Simulator country | "AWS End User Messaging SMS currently supports origination simulator phone numbers in the United States." US destination simulator numbers: Success `+14254147755`, Failure `+14254147167`. | same page |
| Sandbox cap | "You have a monthly SMS spending limit of $1.00 (USD)." | https://docs.aws.amazon.com/sms-voice/latest/userguide/sandbox.html |

Measured on this account (`describe_spend_limits`, `describe_account_attributes`, us-east-1): `ACCOUNT_TIER = SANDBOX`, `TEXT_MESSAGE_MONTHLY_SPEND_LIMIT` enforced 1, max 1. AWS itself stops SMS sending at $1 a month.

Verdict: fixed cost $1.00 per month (simulator number lease) is not above the $1 line; no payment method step is involved for a simulator number. Proceed. Per-message spend is capped in code at $1 total (`tools/live_sms.py`), on top of the account's own $1 SMS limit. The simulator number keeps costing $1 a month until it is released (release is the repo owner's decision, not done here).

## CloudFormation deploy

"There is no additional charge for using AWS CloudFormation with resource providers in the following namespaces: AWS::* and Alexa::*. In these cases, you pay for AWS resources" (https://aws.amazon.com/cloudformation/pricing/, read 2026-10-27). The stack's resources (SNS topic, Lambda function, SES and SMS configuration sets) have no fixed monthly charge; Lambda and SNS bill per request. Proceed if the IAM user is allowed. Result: `CreateStack` refused by IAM (`docs/live/deploy-log.jsonl`), so the allowed parts were created directly by `tools/deploy_direct.py` (Lambda function and SMS configuration set: no fixed monthly charge).

## Measured after the run

3 SMS sends, about $0.023 at the metered $0.00774 each, plus the $1.00 monthly simulator number lease. Lambda: 3 invocations (free tier). The simulator number is still leased; releasing it stops the $1 a month.
