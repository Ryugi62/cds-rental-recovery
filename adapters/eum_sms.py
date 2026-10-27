"""AWS End User Messaging SMS adapter (pinpoint-sms-voice-v2) and its event parser."""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional, Tuple

from domain.models import Channel, DeliveryEvent, EventKind, OutboundRequest

# Event types from the End User Messaging SMS docs (configuration-sets-event-types). There is no opt-out event type:
# a customer's STOP arrives as a two-way inbound message, handled by parse_sms_inbound.
_KIND = {"TEXT_DELIVERED": EventKind.DELIVERY, "TEXT_BLOCKED": EventKind.BOUNCE, "TEXT_CARRIER_BLOCKED": EventKind.BOUNCE,
         "TEXT_UNREACHABLE": EventKind.BOUNCE, "TEXT_CARRIER_UNREACHABLE": EventKind.BOUNCE,
         "TEXT_INVALID": EventKind.BOUNCE}
_STOP_WORDS = {"STOP", "STOPALL", "UNSUBSCRIBE", "CANCEL", "END", "QUIT", "OPTOUT", "OPT-OUT"}


class EumSmsSender:
    channel = Channel.SMS

    def __init__(self, client, origination_identity: str, configuration_set: Optional[str] = None,
                 max_price_per_part: Optional[str] = None):
        self._client, self._origin = client, origination_identity
        self._config_set, self._max_price = configuration_set, max_price_per_part

    def send(self, req: OutboundRequest) -> str:
        if req.channel is not Channel.SMS:
            raise ValueError("EumSmsSender only sends SMS")
        kwargs = dict(DestinationPhoneNumber=req.recipient, OriginationIdentity=self._origin,
                      MessageBody=req.text, MessageType="TRANSACTIONAL")
        if self._config_set:
            kwargs["ConfigurationSetName"] = self._config_set
        if self._max_price:
            kwargs["MaxPrice"] = self._max_price  # provider refuses a part priced above this (USD)
        return self._client.send_text_message(**kwargs)["MessageId"]


class SmsOptOutList:
    """The account's SMS opt-out list read back as OPT_OUT events (a STOP reply lands here even with no event
    destination). Only the numbers asked about are looked up."""

    def __init__(self, client, list_name: str = "Default"):
        self._client, self._list = client, list_name

    def poll(self, numbers: List[str], at: datetime) -> List[DeliveryEvent]:
        if not numbers:
            return []
        resp = self._client.describe_opted_out_numbers(OptOutListName=self._list, OptedOutNumbers=list(numbers))
        return [DeliveryEvent(EventKind.OPT_OUT, Channel.SMS, n["OptedOutNumber"], at, None)
                for n in resp.get("OptedOutNumbers", [])]


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
