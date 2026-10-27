# Offering: how a partner sells this again and again

**Who pays:** a small equipment-rental shop (cameras, tools, event gear) that chases overdue returns by phone and text today.
**Price:** USD 0.25 per thread that closes without a person (reply read, matched to the ledger, posted). Threads handed to a person cost nothing. AWS usage (SES $0.10 per 1,000 emails, SMS by country) is billed by AWS to the shop's own account.
**Why that price:** at the US federal minimum wage ($7.25, dol.gov) a closed thread saves about USD 0.73 (6 minutes, `docs/ROI.md`; the Korean figure, 1,032 KRW, is in the same file); the shop keeps about two thirds of the saving even at the lowest wage, and pays nothing when the reader closes nothing.
**Install steps (per shop):** 1) `sam deploy` from `AGENTS.md` into the shop's AWS account, 2) verify the shop's sender address or domain, 3) import the ledger of overdue items (CSV columns: item, customer, quantity, due date, email, phone, consent per channel), 4) set quiet hours and daily cap, 5) run the preflight and post-deploy checks.
**Throughput limits:** SES sandbox 200 emails per 24 h and 1 per second until production access; the gate caps each customer at 2 messages per day; the regex reader takes about 0.01 ms per reply (measured 2026-10-26 on a laptop, 2,000 runs; no model call), so reading is never the limit.
**ACE opportunity:** to be registered in AWS Partner Central under the hackathon campaign before submission (ID added here then).

## Plan

| Date | Milestone | People and resources | Target (number) |
|---|---|---|---|
| 2026-10-27 | Hackathon submission | 1 developer, remote; existing AWS account | live SES sends ≥ 4 with events read back (done: 4) |
| 2026-11-15 | SES receiving on a verified domain: first full round trip by SES | 1 developer; 1 domain (cost decision by the owner) | ≥ 1 reply received by SES and read into the ledger |
| 2026-11-30 | Reader checked on a larger labelled set | 1 developer | 50 synthetic replies, auto-closed against the label = 0 |
| 2026-12-31 | Pilot with one rental shop that agrees in writing, on its own AWS account | 1 developer + 1 shop | ≥ 20 real threads; close rate and hand-off rate reported |
