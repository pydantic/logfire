from typing import Any

import requests
from opentelemetry.sdk.metrics._internal.export import MetricExportResult
from opentelemetry.sdk.metrics._internal.point import MetricsData

from ..utils import logger
from .wrapper import WrapperMetricExporter


class QuietMetricExporter(WrapperMetricExporter):
    def export(self, metrics_data: MetricsData, timeout_millis: float = 10_000, **kwargs: Any) -> MetricExportResult:
        try:
            return super().export(metrics_data, timeout_millis, **kwargs)
        except requests.exceptions.RequestException as e:
            logger.warning('Error sending metrics to Logfire: %s', e)
            return MetricExportResult.FAILURE
