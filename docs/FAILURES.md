# Failure types: every one ends somewhere a person can see

No silent failures: each row ends in a visible state (BLOCK, HOLD, APPROVAL queue, or a HANDOFF item with a reason) and is pinned by a test. `tests/test_failures.py` fails if a test named here does not exist.

| # | Failure | What happens | Where it shows | Test |
|---|---|---|---|---|
| 1 | Hard bounce (SES `Bounce`, Permanent) | Address blocked; SMS suggested if the customer has it, otherwise hand-off | Gate screen step "bounce", BLOCK `address_blocked` on retry | `test_g8_bounce_blocks_address_and_suggests_sms`, `test_bounce_with_no_other_channel_hands_off` |
| 2 | Transient bounce | Ignored on purpose: SES retries it; no address block | Event log only | `test_ses_event_transient_bounce_ignored` |
| 3 | Complaint or STOP (opt-out) | Customer opted out on every channel; thread handed off | BLOCK `opt_out` on any later send, provider calls 0 | `test_g9_opt_out_blocks_every_channel_and_hands_off`, `test_send_after_opt_out_is_blocked_with_zero_provider_calls` |
| 4 | Provider error or throttling on send | Not counted as a send, not retried blindly; thread handed off with the error text | `SEND_FAILED` log row, HANDOFF `send_failed` | `test_provider_error_does_not_crash_and_hands_off_with_reason`, `test_provider_error_is_not_counted_as_a_send` |
| 5 | Reader unsure (no date or no quantity) | No ledger write; hand-off | HANDOFF with reason `low_confidence` | `test_g7_low_confidence_hands_off`, `test_no_date_means_low_confidence` |
| 6 | Reply disagrees with the ledger | No ledger write; hand-off with both numbers | HANDOFF with reason `quantity_mismatch` | `test_g7_mismatch_hands_off_with_reason_no_posting`, `test_a_wrong_quantity_is_never_auto_closed` |
| 7 | Over-sending (third message in a day) | Blocked before the provider | BLOCK `daily_cap`, provider calls 0 | `test_g3_third_send_blocked_no_sender_call` |
| 8 | Quiet hours | Held with a release time | HOLD with "Releases" time | `test_g4_quiet_hours_hold_no_send` |
| 9 | Money or legal wording | Waits for a person; agent cannot approve itself | APPROVAL queue | `test_g4_approval_waits_for_human_then_sends`, `test_agent_cannot_self_approve` |
| 10 | No consent for the channel | Blocked | BLOCK `no_consent` | `test_block_when_no_consent` |
| 11 | Agent tries to send around the gate | No code path exists | Layer test | `test_g11_no_path_to_sender_except_gate` |
| 12 | Reply-reading model refused, throttled or answers in the wrong shape (Bedrock) | Logged `ASSIST_FAILED`; the reply falls back to the regex reading and a low-confidence reply is handed off | Hand-off item `low_confidence`; live example in `docs/live/bedrock-log.jsonl` (IAM refusal) | `test_g13_assist_failure_is_logged_and_hands_off`, `test_g13_bedrock_non_json_raises`, `test_g13_bedrock_bad_types_raise` |
| 13 | Model invents a quantity the customer did not write | Answer not used (grounding check); hand-off | Hand-off item | `test_g13_invented_quantity_is_rejected`, `test_g13_invented_quantity_hands_off` |
| 14 | The date (from the reader or a model) falls on a different weekday than the one the customer wrote ("saturday" read as a Friday date) | Not posted; no follow-up is sent; hand-off | Hand-off item `weekday_mismatch`; live example in `docs/live/bedrock-log.jsonl` lines 9-10 | `test_g13_model_date_with_wrong_weekday_is_handed_off_not_posted`, `test_g13_regex_reader_iso_date_with_wrong_weekday_is_handed_off` |

Across 14 synthetic reply variants every thread ended CLOSED or HANDOFF, none silent: `test_every_variant_ends_closed_or_handed_off_never_silent`.
