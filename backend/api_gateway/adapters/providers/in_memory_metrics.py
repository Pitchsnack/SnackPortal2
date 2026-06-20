"""In-memory, vendor-neutral request/latency metrics recorder (stdlib) — WP-11 default.

Implements ``MetricsPort`` with NO provider observability SDK (datadog/opentelemetry/
prometheus/sentry/etc.) and NO tenant-disclosing label (IC-010 §S): it records the
operational ``RequestMetric`` labels only (category/outcome/status/duration). In-process
only — not a persistence sink; the dev/test default.
"""

from __future__ import annotations

from typing import List

from ...models import RequestMetric
from ...ports import MetricsPort


class InMemoryMetrics(MetricsPort):
    def __init__(self) -> None:
        self._records: List[RequestMetric] = []

    def record_request(self, metric: RequestMetric) -> None:
        self._records.append(metric)

    def records(self) -> List[RequestMetric]:
        return list(self._records)
