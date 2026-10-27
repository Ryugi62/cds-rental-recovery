# Live log excerpt (docs/live/live-log.jsonl, lines)
- 1-4 SEND x4, verdict PASS, SES MessageIds returned (owner, success@, bounce@, complaint@ simulator)
- 5-7 self: EVENTS DELIVERY, DECISION nudge timer, RETRY_SEND PASS
- 8-10 success@: DELIVERY, RETRY_SEND PASS
- 11-13 bounce@: BOUNCE -> block_address + handoff, RETRY_SEND BLOCK address_blocked (ses_called false)
- 14-17 complaint@: DELIVERY + OPT_OUT -> opt_out_customer + handoff, RETRY_SEND BLOCK opt_out (ses_called false)
- 18-19 REPLY_READ qty 3 / 2026-10-29 / conf 0.9 / match, POSTED -> CLOSED (reply text came from the owner inbox via Gmail, not SES receiving)

# SMS log excerpt (docs/live/sms-log.jsonl, lines), 2026-10-27
- 1 COST_CHECK: simulator number $1/month, account SMS limit $1/month, proceed (docs/live/cost-check.md)
- 2 REQUEST_SIMULATOR_NUMBER: US SIMULATOR origination number, MonthlyLeasingPrice 1.00
- 3-6 success simulator number: SMS_SEND PASS, CloudWatch AWS/SMSVoice sent 1 / delivered 1 -> DELIVERY, nudge timer, RETRY PASS (second real send). Line 4 used the first window rule (send time minus 1 min); no earlier send existed, so the count is the same
- 7 failure simulator number: SMS_SEND PASS
- 8-11 opt-out: owner lists the success number in the Default opt-out list (a simulator cannot reply STOP), list read back -> OPT_OUT, hand-off, retry BLOCK opt_out, SMS calls 0
- 12-14 failure simulator number settled after the 10 min window: sent 1, delivered 0 after 10 min: BOUNCE | bounced and no other channel, hand-off | BLOCK address_blocked, SMS calls 0

# Deploy log excerpt (docs/live/deploy-log.jsonl, lines), 2026-10-27
- 1 CloudFormation CreateStack refused (AccessDenied)
- 2 SMS configuration set cds-rr-sms created; 3 SNS CreateTopic refused (AuthorizationError)
- 4 Lambda cds-rr-events created (python3.12, events_handler, existing logs-only role, no IAM change)
- 5-7 Lambda invoked: SMS delivery shape with the real message id -> DELIVERY decision; SES bounce -> block address, suggest SMS; unknown type -> ignored 1
