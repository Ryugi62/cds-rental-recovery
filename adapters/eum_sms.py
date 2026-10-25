"""AWS End User Messaging SMS adapter (pinpoint-sms-voice-v2) and its event parser."""
from __future__ import annotations

from datetime import datetime
from typing import Optional, Tuple

from domain.models import Channel, DeliveryEvent, EventKind, OutboundRequest

# Event types from the End User Messaging SMS docs (configuration-sets-event-types). There is no opt-out event type:
# a customer's STOP arrives as a two-way inbound message, handled by parse_sms_inbound.
_KIND = {"TEXT_DELIVERED": EventKind.DELIVERY, "TEXT_BLOCKED": EventKind.BOUNCE, "TEXT_CARRIER_BLOCKED": EventKind.BOUNCE,
         "TEXT_UNREACHABLE": EventKind.BOUNCE, "TEXT_CARRIER_UNREACHABLE": EventKind.BOUNCE,
         "TEXT_INVALID": EventKind.BOUNCE}
_STOP_WORDS = {"STOP", "STOPALL", "UNSUBSCRIBE", "CANCEL", "END", "QUIT", "OPTOUT", "OPT-OUT"}


class EumSmsSender:
    channel = Channel.SMS

    def __init__(self, client, origination_identity: str):
        self._client, self._origin = client, origination_identity

    def send(self, req: OutboundRequest) -> str:
        if req.channel is not Channel.SMS:
            raise ValueError("EumSmsSender only sends SMS")
        resp = self._client.send_text_message(
            DestinationPhoneNumber=req.recipient,
            OriginationIdentity=self._origin,
            MessageBody=req.text,
            MessageType="TRANSACTIONAL",
        )
        return resp["MessageId"]


def parse_sms_event(payload: dict) -> Optional[DeliveryEvent]:
    kind = _KIND.get(payload.get("eventType", ""))
    if kind is None:
        return None
    at = datetime.utcfromtimestamp(payload["eventTimestamp"] / 1000)
    return DeliveryEvent(kind, Channel.SMS, payload["destinationPhoneNumber"], at, payload.get("messageId"))


def parse_sms_inbound(payload: dict, at: datetime) -> Tuple[Optional[DeliveryEvent], Optional[str]]:
    """Two-way SMS message from SNS. STOP-type keyword -> OPT_OUT event; anything else -> reply text for the reader."""
    body = (payload.get("messageBody") or "").strip()
    sender = payload["originationNumber"]
    if body.upper() in _STOP_WORDS:
        return DeliveryEvent(EventKind.OPT_OUT, Channel.SMS, sender, at, payload.get("inboundMessageId")), None
    return None, body
