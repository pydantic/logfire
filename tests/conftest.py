import pytest
from opentelemetry import trace
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.trace.export import SimpleSpanProcessor

from logfire._config import configure
from logfire.testing import (
    IncrementalIdGenerator,
    TestExporter,
    TimeGenerator,
)


@pytest.fixture
def id_generator() -> IncrementalIdGenerator:
    return IncrementalIdGenerator()


@pytest.fixture
def time_generator() -> TimeGenerator:
    return TimeGenerator()


@pytest.fixture
def exporter() -> TestExporter:
    return TestExporter()


@pytest.fixture
def metrics_reader() -> InMemoryMetricReader:
    return InMemoryMetricReader()


@pytest.fixture(autouse=True)
def config(
    exporter: TestExporter,
    metrics_reader: InMemoryMetricReader,
    id_generator: IncrementalIdGenerator,
    time_generator: TimeGenerator,
) -> None:
    configure(
        send_to_logfire=False,
        console_print='off',
        id_generator=id_generator,
        ns_timestamp_generator=time_generator,
        processors=[SimpleSpanProcessor(exporter)],
        metric_readers=[metrics_reader],
    )
    # sanity check: there are no active spans
    # if there are, it means that some test forgot to close them
    # which may mess with other tests
    span = trace.get_current_span()
    assert span is trace.INVALID_SPAN


@pytest.fixture(autouse=True)
def clear_pydantic_plugins_cache():
    """Clear any existing Pydantic plugins."""
    from pydantic.plugin import _loader

    assert _loader._loading_plugins is False  # type: ignore
    _loader._plugins = None  # type: ignore
