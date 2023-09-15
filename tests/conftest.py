from collections.abc import Sequence

import pytest
from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export import SpanExporter

from logfire import Logfire
from logfire.config import LogfireConfig


class TestExporter(SpanExporter):
    # NOTE: Avoid test discovery by pytest.
    __test__ = False

    def __init__(self) -> None:
        self.exported_spans: list[ReadableSpan] = []

    def export(self, spans: Sequence[ReadableSpan]) -> None:  # type: ignore[override]
        self.exported_spans = list(spans)


@pytest.fixture
def exporter() -> TestExporter:
    return TestExporter()


@pytest.fixture
def config(exporter: TestExporter) -> LogfireConfig:
    return LogfireConfig.from_exports(exporter, service_name='logfire-sdk-testing')


@pytest.fixture
def logfire(config: LogfireConfig) -> Logfire:
    return Logfire(config)
