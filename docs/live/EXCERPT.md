# Live log excerpt (docs/live/live-log.jsonl, lines)
- 1-4 SEND x4, verdict PASS, SES MessageIds returned (owner, success@, bounce@, complaint@ simulator)
- 5-7 self: EVENTS DELIVERY, DECISION nudge timer, RETRY_SEND PASS
- 8-10 success@: DELIVERY, RETRY_SEND PASS
- 11-13 bounce@: BOUNCE -> block_address + handoff, RETRY_SEND BLOCK address_blocked (ses_called false)
- 14-17 complaint@: DELIVERY + OPT_OUT -> opt_out_customer + handoff, RETRY_SEND BLOCK opt_out (ses_called false)
- 18-19 REPLY_READ qty 3 / 2026-10-29 / conf 0.9 / match, POSTED -> CLOSED (reply text came from the owner inbox via Gmail, not SES receiving)
