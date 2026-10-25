"""Lambda entry points wired by template.yaml. Each SNS record becomes one JSON log line (CloudWatch Logs).

events_handler: SES configuration-set events and End User Messaging SMS events -> decision (block, opt-out, nudge, hand-off).
inbound_handler: SES receiving (SNS action) -> reply reading (quantity, date, confidence).
Unknown messages are counted and logged, never dropped silently.
"""
from __future__ import annotations

import json
from datetime import datetime

from adapters.eum_sms import parse_sms_event
from adapters.ses import parse_inbound_notification, parse_ses_event
from domain.events import decide_after_event
from domain.models import Channel
from domain.reading import read_reply


def _messages(event):
    for rec in event.get("Records", []):
        sns = rec.get("Sns", {})
        yield sns.get("Timestamp", ""), json.loads(sns.get("Message", "{}"))


def events_handler(event, context):
    decisions, ignored = [], 0
    for _, msg in _messages(event):
        ev = parse_ses_event(msg) if ("eventType" in msg and "mail" in msg) or "notificationType" in msg else parse_sms_event(msg)
        if ev is None:
            ignored += 1
            print(json.dumps({"kind": "IGNORED", "type": msg.get("eventType") or msg.get("notificationType")}))
            continue
        d = decide_after_event(ev, [Channel.EMAIL, Channel.SMS])
        row = {"kind": ev.kind.value, "channel": ev.channel.value, "message_id": ev.message_id,
               "block_address": d.block_address, "opt_out_customer": d.opt_out_customer, "handoff": d.handoff,
               "suggest": d.suggest_channel.value if d.suggest_channel else None, "note": d.note}
        print(json.dumps(row))
        decisions.append(row)
    return {"decisions": decisions, "ignored": ignored}


def inbound_handler(event, context):
    readings = []
    for ts, msg in _messages(event):
        mail = parse_inbound_notification(msg)
        today = datetime.strptime(ts[:10], "%Y-%m-%d").date() if ts else datetime.utcnow().date()
        r = read_reply(mail.text, today)
        row = {"message_id": mail.message_id, "quantity": r.quantity,
               "return_date": r.return_date.isoformat() if r.return_date else None, "confidence": r.confidence}
        print(json.dumps(row))
        readings.append(row)
    return {"readings": readings}
