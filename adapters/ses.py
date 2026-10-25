"""SES adapters: send, inbound (SNS notification with raw content), delivery/bounce/complaint events."""
from __future__ import annotations

import json
from datetime import datetime
from email import message_from_string
from email.policy import default
from typing import Optional

from application.ports import InboundMail
from domain.models import Channel, DeliveryEvent, EventKind, OutboundRequest

SUBJECT = "Equipment return check"


class SesEmailSender:
    channel = Channel.EMAIL

    def __init__(self, client, source: str, config_set: Optional[str] = None, tags: Optional[dict] = None):
        self._client, self._source, self._config_set, self._tags = client, source, config_set, tags

    def send(self, req: OutboundRequest) -> str:
        if req.channel is not Channel.EMAIL:
            raise ValueError("SesEmailSender only sends EMAIL")
        kwargs = dict(
            Source=self._source,
            Destination={"ToAddresses": [req.recipient]},
            Message={"Subject": {"Data": SUBJECT}, "Body": {"Text": {"Data": req.text}}},
        )
        if self._config_set:
            kwargs["ConfigurationSetName"] = self._config_set
        if self._tags:
            kwargs["Tags"] = [{"Name": k, "Value": v} for k, v in self._tags.items()]
        resp = self._client.send_email(**kwargs)
        return resp["MessageId"]


def _inner(note: dict) -> dict:
    msg = note.get("Message", note)
    return json.loads(msg) if isinstance(msg, str) else msg


def parse_inbound_notification(note: dict) -> InboundMail:
    body = _inner(note)
    parsed = message_from_string(body.get("content", ""), policy=default)
    part = parsed.get_body(preferencelist=("plain",))
    text = part.get_content() if part is not None else ""
    return InboundMail(
        sender=body["mail"]["source"],
        subject=str(parsed.get("Subject", "")),
        text=text.strip() if text else "",
        message_id=body["mail"]["messageId"],
    )


def _ts(value: str) -> datetime:
    return datetime.strptime(value[:19], "%Y-%m-%dT%H:%M:%S")


def parse_ses_event(note: dict) -> Optional[DeliveryEvent]:
    b = _inner(note)
    kind = b.get("eventType") or b.get("notificationType")
    mid = b.get("mail", {}).get("messageId")
    if kind == "Delivery":
        d = b["delivery"]
        return DeliveryEvent(EventKind.DELIVERY, Channel.EMAIL, d["recipients"][0], _ts(d["timestamp"]), mid)
    if kind == "Bounce":
        d = b["bounce"]
        if d.get("bounceType") != "Permanent":
            return None
        return DeliveryEvent(EventKind.BOUNCE, Channel.EMAIL, d["bouncedRecipients"][0]["emailAddress"], _ts(d["timestamp"]), mid)
    if kind == "Complaint":
        d = b["complaint"]
        return DeliveryEvent(EventKind.OPT_OUT, Channel.EMAIL, d["complainedRecipients"][0]["emailAddress"], _ts(d["timestamp"]), mid)
    return None
