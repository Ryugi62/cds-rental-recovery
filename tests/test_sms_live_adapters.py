"""End User Messaging SMS live-path adapters against stub clients: spend cap per part, configuration set,
and the account opt-out list read back as OPT_OUT events. No network."""
from datetime import datetime, timedelta

from adapters.eum_sms import EumSmsSender, SmsOptOutList
from domain.models import Channel, EventKind, OutboundRequest, Requester


class StubEum:
    def __init__(self, opted_out=()):
        self.calls, self.opted_out = [], set(opted_out)

    def send_text_message(self, **kw):
        self.calls.append(kw)
        return {"MessageId": "eum-1"}

    def describe_opted_out_numbers(self, OptOutListName, OptedOutNumbers):
        self.calls.append({"list": OptOutListName, "numbers": OptedOutNumbers})
        return {"OptOutListName": OptOutListName,
                "OptedOutNumbers": [{"OptedOutNumber": n, "EndUserOptedOut": False} for n in OptedOutNumbers
                                    if n in self.opted_out]}


def sms(to="+10000000001"):
    return OutboundRequest(Channel.SMS, to, "Return check", Requester.HUMAN)


def test_sender_passes_configuration_set_and_max_price_per_part():
    c = StubEum()
    EumSmsSender(c, "phone-1", configuration_set="cds-rr-sms", max_price_per_part="0.02").send(sms())
    kw = c.calls[0]
    assert kw["ConfigurationSetName"] == "cds-rr-sms" and kw["MaxPrice"] == "0.02"
    assert kw["OriginationIdentity"] == "phone-1" and kw["MessageType"] == "TRANSACTIONAL"


def test_sender_without_options_sends_no_optional_keys():
    c = StubEum()
    EumSmsSender(c, "phone-1").send(sms())
    assert "ConfigurationSetName" not in c.calls[0] and "MaxPrice" not in c.calls[0]


def test_opt_out_list_returns_opt_out_event_only_for_listed_numbers():
    at = datetime(2026, 10, 27, 12, 0)
    events = SmsOptOutList(StubEum(opted_out={"+10000000002"}), "Default").poll(["+10000000001", "+10000000002"], at)
    assert [(e.kind, e.channel, e.address, e.at) for e in events] == [(EventKind.OPT_OUT, Channel.SMS, "+10000000002", at)]


def test_opt_out_list_with_no_numbers_makes_no_call():
    c = StubEum()
    assert SmsOptOutList(c, "Default").poll([], datetime(2026, 10, 27)) == [] and c.calls == []


class StubCloudWatch:
    def __init__(self, sums):
        self.sums, self.calls = sums, []

    def get_metric_data(self, **kw):
        self.calls.append(kw)
        out = []
        for q in kw["MetricDataQueries"]:
            v = self.sums.get(q["MetricStat"]["Metric"]["MetricName"])
            out.append({"Id": q["Id"], "Values": [] if v is None else [v], "StatusCode": "Complete"})
        return {"MetricDataResults": out}


def test_sms_delivery_metric_becomes_delivery_event():
    from adapters.sms_metrics import CloudWatchSmsDelivery
    sent_at = datetime(2026, 10, 27, 11, 0)
    cw = StubCloudWatch({"NumberOfTextMessagePartsSent": 1, "NumberOfTextMessagePartsDelivered": 1})
    r = CloudWatchSmsDelivery(cw).read(sent_at, "+10000000001", sent_at + timedelta(minutes=3))
    assert (r.sent, r.delivered) == (1, 1)
    assert (r.event.kind, r.event.channel, r.event.address) == (EventKind.DELIVERY, Channel.SMS, "+10000000001")
    q = cw.calls[0]["MetricDataQueries"][0]["MetricStat"]
    assert q["Metric"]["Namespace"] == "AWS/SMSVoice" and q["Stat"] == "Sum" and cw.calls[0]["StartTime"] <= sent_at


def test_sent_but_not_delivered_after_settle_window_is_bounce_and_before_it_is_undecided():
    from adapters.sms_metrics import CloudWatchSmsDelivery
    sent_at = datetime(2026, 10, 27, 11, 0)
    cw = StubCloudWatch({"NumberOfTextMessagePartsSent": 1})
    early = CloudWatchSmsDelivery(cw, settle_minutes=10).read(sent_at, "+1", sent_at + timedelta(minutes=4))
    late = CloudWatchSmsDelivery(cw, settle_minutes=10).read(sent_at, "+1", sent_at + timedelta(minutes=11))
    assert early.event is None and late.event.kind is EventKind.BOUNCE


def test_no_datapoint_at_all_is_undecided():
    from adapters.sms_metrics import CloudWatchSmsDelivery
    sent_at = datetime(2026, 10, 27, 11, 0)
    r = CloudWatchSmsDelivery(StubCloudWatch({})).read(sent_at, "+1", sent_at + timedelta(hours=1))
    assert (r.sent, r.delivered, r.event) == (0, 0, None)


def test_window_starts_at_the_send_minute_so_an_earlier_send_is_not_counted():
    from adapters.sms_metrics import CloudWatchSmsDelivery
    sent_at = datetime(2026, 10, 27, 10, 47, 12)
    cw = StubCloudWatch({"NumberOfTextMessagePartsSent": 1})
    CloudWatchSmsDelivery(cw).read(sent_at, "+1", sent_at + timedelta(minutes=2))
    assert cw.calls[0]["StartTime"] == datetime(2026, 10, 27, 10, 47, 0)
