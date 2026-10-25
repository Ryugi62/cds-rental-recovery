"""Adapters against stub AWS clients and canned SNS payloads. No network, no boto3 calls."""
import json
from datetime import datetime
import pytest
from adapters.ses import SesEmailSender, parse_inbound_notification, parse_ses_event
from adapters.eum_sms import EumSmsSender, parse_sms_event
from adapters.fakes import FakeSender
from domain.models import Channel, EventKind, OutboundRequest, Requester
from infrastructure.aws_clients import make_client


class StubSes:
    def __init__(self):
        self.calls = []

    def send_email(self, **kw):
        self.calls.append(kw)
        return {"MessageId": "ses-abc"}


class StubEum:
    def __init__(self):
        self.calls = []

    def send_text_message(self, **kw):
        self.calls.append(kw)
        return {"MessageId": "eum-xyz"}


def email_req():
    return OutboundRequest(Channel.EMAIL, "c1@example.test", "Please confirm return.", Requester.HUMAN)


def test_ses_sender_builds_request_and_returns_message_id():
    c = StubSes()
    mid = SesEmailSender(c, "desk@example.test").send(email_req())
    assert mid == "ses-abc"
    kw = c.calls[0]
    assert kw["Source"] == "desk@example.test" and kw["Destination"]["ToAddresses"] == ["c1@example.test"]
    assert kw["Message"]["Body"]["Text"]["Data"] == "Please confirm return."


def test_ses_sender_refuses_wrong_channel():
    with pytest.raises(ValueError):
        SesEmailSender(StubSes(), "a@b.test").send(OutboundRequest(Channel.SMS, "+1", "x", Requester.HUMAN))


def test_eum_sender_builds_request():
    c = StubEum()
    mid = EumSmsSender(c, "+10000000000").send(OutboundRequest(Channel.SMS, "+10000000001", "hello", Requester.HUMAN))
    assert mid == "eum-xyz"
    kw = c.calls[0]
    assert kw["DestinationPhoneNumber"] == "+10000000001" and kw["MessageBody"] == "hello"
    assert kw["OriginationIdentity"] == "+10000000000"


RAW = "From: Cust <c1@example.test>\r\nTo: desk@example.test\r\nSubject: Re: Return\r\nMessage-ID: <m1@x>\r\n\r\nI'll bring 3 on Thursday\r\n"


def sns(message: dict) -> dict:
    return {"Type": "Notification", "Message": json.dumps(message)}


def test_parse_inbound_notification_extracts_sender_and_body():
    note = sns({"notificationType": "Received", "mail": {"source": "c1@example.test", "messageId": "ses-in-1"}, "content": RAW})
    m = parse_inbound_notification(note)
    assert m.sender == "c1@example.test" and "bring 3 on Thursday" in m.text and m.message_id == "ses-in-1"


def test_parse_inbound_multipart_prefers_plain_text():
    raw = ("From: c1@example.test\r\nSubject: R\r\nMIME-Version: 1.0\r\nContent-Type: multipart/alternative; boundary=B\r\n\r\n"
           "--B\r\nContent-Type: text/html\r\n\r\n<p>html</p>\r\n--B\r\nContent-Type: text/plain\r\n\r\nplain 3 Thursday\r\n--B--\r\n")
    m = parse_inbound_notification(sns({"mail": {"source": "c1@example.test", "messageId": "i2"}, "content": raw}))
    assert m.text.strip() == "plain 3 Thursday"


def test_ses_event_delivery():
    ev = parse_ses_event(sns({"eventType": "Delivery", "mail": {"messageId": "ses-abc"},
                              "delivery": {"recipients": ["c1@example.test"], "timestamp": "2026-10-22T03:05:00.000Z"}}))
    assert ev.kind is EventKind.DELIVERY and ev.address == "c1@example.test" and ev.channel is Channel.EMAIL
    assert ev.message_id == "ses-abc"


def test_ses_event_permanent_bounce():
    ev = parse_ses_event(sns({"eventType": "Bounce", "mail": {"messageId": "m"},
                              "bounce": {"bounceType": "Permanent", "bouncedRecipients": [{"emailAddress": "bounce@simulator.amazonses.com"}],
                                         "timestamp": "2026-10-22T03:05:00.000Z"}}))
    assert ev.kind is EventKind.BOUNCE and ev.address == "bounce@simulator.amazonses.com"


def test_ses_event_transient_bounce_ignored():
    ev = parse_ses_event(sns({"eventType": "Bounce", "mail": {"messageId": "m"},
                              "bounce": {"bounceType": "Transient", "bouncedRecipients": [{"emailAddress": "a@b.test"}],
                                         "timestamp": "2026-10-22T03:05:00.000Z"}}))
    assert ev is None


def test_ses_event_complaint_is_opt_out():
    ev = parse_ses_event(sns({"eventType": "Complaint", "mail": {"messageId": "m"},
                              "complaint": {"complainedRecipients": [{"emailAddress": "complaint@simulator.amazonses.com"}],
                                            "timestamp": "2026-10-22T03:05:00.000Z"}}))
    assert ev.kind is EventKind.OPT_OUT


def test_sms_event_stop_and_delivery_and_failure():
    base = {"destinationPhoneNumber": "+10000000001", "eventTimestamp": 1792638000000, "messageId": "eum-xyz"}
    assert parse_sms_event({**base, "eventType": "TEXT_DELIVERED"}).kind is EventKind.DELIVERY
    assert parse_sms_event({**base, "eventType": "TEXT_BLOCKED"}).kind is EventKind.BOUNCE
    assert parse_sms_event({**base, "eventType": "TEXT_UNREACHABLE"}).kind is EventKind.BOUNCE
    assert parse_sms_event({**base, "eventType": "TEXT_QUEUED"}) is None
    assert parse_sms_event({"eventType": "OPT_OUT", "destinationPhoneNumber": "+10000000001", "eventTimestamp": 1}).kind is EventKind.OPT_OUT


def test_make_client_is_lazy_and_does_not_call():
    seen = {}

    class FakeBoto:
        @staticmethod
        def client(name, region_name=None):
            seen["args"] = (name, region_name)
            return object()

    c = make_client("ses", "us-east-1", boto3_module=FakeBoto)
    assert seen["args"] == ("ses", "us-east-1") and c is not None


def test_fake_sender_records_calls():
    s = FakeSender(Channel.EMAIL); s.send(email_req())
    assert len(s.calls) == 1


# --- live-run support: config set + tags on send, CloudWatch metric events -------------------------------------
def test_ses_sender_passes_config_set_and_tags():
    c = StubSes()
    SesEmailSender(c, "desk@example.test", config_set="cds-rr", tags={"case": "t1"}).send(email_req())
    kw = c.calls[0]
    assert kw["ConfigurationSetName"] == "cds-rr" and kw["Tags"] == [{"Name": "case", "Value": "t1"}]


def test_ses_sender_without_config_set_sends_no_extra_keys():
    c = StubSes()
    SesEmailSender(c, "desk@example.test").send(email_req())
    assert "ConfigurationSetName" not in c.calls[0] and "Tags" not in c.calls[0]


class StubCw:
    """list_metrics only returns metrics that have received data, so presence == the event happened."""
    def __init__(self, present):
        self.present, self.calls = present, []

    def list_metrics(self, **kw):
        self.calls.append(kw)
        return {"Metrics": [{"Namespace": kw["Namespace"], "MetricName": kw["MetricName"]}] if kw["MetricName"] in self.present else []}


def _poll(present, tag="t1"):
    from adapters.ses_metrics import CloudWatchSesEvents
    return CloudWatchSesEvents(StubCw(present), dimension="case").poll(tag, "c1@example.test")


def test_cloudwatch_events_turn_present_metrics_into_delivery_events():
    evs = _poll({"Delivery"})
    assert [e.kind for e in evs] == [EventKind.DELIVERY] and evs[0].address == "c1@example.test"


def test_cloudwatch_events_map_bounce_and_complaint():
    assert {e.kind for e in _poll({"Bounce", "Complaint"})} == {EventKind.BOUNCE, EventKind.OPT_OUT}


def test_cloudwatch_events_empty_when_no_metric():
    assert _poll(set()) == []


def test_cloudwatch_events_filter_by_tag_dimension():
    from adapters.ses_metrics import CloudWatchSesEvents
    c = StubCw({"Delivery"})
    CloudWatchSesEvents(c, dimension="case").poll("t9", "a@x.test")
    assert c.calls[0]["Dimensions"] == [{"Name": "case", "Value": "t9"}]
