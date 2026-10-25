"""SES events read back from CloudWatch (config set with a CloudWatch destination, message-tag dimension).
Used when no SNS topic is available. ListMetrics only returns metrics that have received data, so a metric that exists
for a tag value means that event happened for it; the recipient address comes from the caller's own send record."""
from __future__ import annotations

from datetime import datetime
from typing import List

from domain.models import Channel, DeliveryEvent, EventKind

_METRICS = (("Delivery", EventKind.DELIVERY), ("Bounce", EventKind.BOUNCE), ("Complaint", EventKind.OPT_OUT))


class CloudWatchSesEvents:
    def __init__(self, client, dimension: str, namespace: str = "AWS/SES"):
        self._client, self._dimension, self._ns = client, dimension, namespace

    def poll(self, tag_value: str, address: str, at: datetime = datetime(1970, 1, 1)) -> List[DeliveryEvent]:
        out = []
        for metric, kind in _METRICS:
            resp = self._client.list_metrics(Namespace=self._ns, MetricName=metric,
                                             Dimensions=[{"Name": self._dimension, "Value": tag_value}])
            if resp.get("Metrics"):
                out.append(DeliveryEvent(kind, Channel.EMAIL, address, at, None))
        return out
