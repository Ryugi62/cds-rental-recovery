"""End User Messaging SMS delivery read back from CloudWatch (namespace AWS/SMSVoice), for accounts where no event
destination can be attached (no SNS, Firehose or log role). The metrics are counts, not per-message records, so the
caller reads one send at a time inside its own window (sends at least one minute apart): delivered parts >= 1 -> DELIVERY; sent but nothing delivered
once the settle window has passed -> BOUNCE (not delivered); otherwise undecided."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import List, Optional

from domain.models import Channel, DeliveryEvent, EventKind

NAMESPACE = "AWS/SMSVoice"


@dataclass(frozen=True)
class SmsMetricReading:
    sent: int
    delivered: int
    start: datetime
    end: datetime
    event: Optional[DeliveryEvent]


class CloudWatchSmsDelivery:
    def __init__(self, client, dimensions: Optional[List[dict]] = None, settle_minutes: int = 10, window_minutes: int = 15):
        self._client, self._dims = client, dimensions or []
        self._settle, self._window = timedelta(minutes=settle_minutes), timedelta(minutes=window_minutes)

    def _sums(self, start: datetime, end: datetime) -> dict:
        names = {"s": "NumberOfTextMessagePartsSent", "d": "NumberOfTextMessagePartsDelivered"}
        queries = [{"Id": i, "MetricStat": {"Metric": {"Namespace": NAMESPACE, "MetricName": m, "Dimensions": self._dims},
                                            "Period": 60, "Stat": "Sum"}} for i, m in names.items()]
        resp = self._client.get_metric_data(MetricDataQueries=queries, StartTime=start, EndTime=end)
        return {r["Id"]: int(sum(r.get("Values", []))) for r in resp.get("MetricDataResults", [])}

    def read(self, sent_at: datetime, address: str, now: datetime) -> SmsMetricReading:
        start = sent_at.replace(second=0, microsecond=0)  # 60 s buckets: an earlier send's minute stays out
        end = min(now, sent_at + self._window)
        sums = self._sums(start, end)
        sent, delivered = sums.get("s", 0), sums.get("d", 0)
        event = None
        if delivered >= 1:
            event = DeliveryEvent(EventKind.DELIVERY, Channel.SMS, address, end, None)
        elif sent >= 1 and now >= sent_at + self._settle:
            event = DeliveryEvent(EventKind.BOUNCE, Channel.SMS, address, end, None)
        return SmsMetricReading(sent, delivered, start, end, event)
