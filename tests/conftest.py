import pytest
from opentelemetry.sdk.trace.export import SimpleSpanProcessor

from logfire import Logfire
from logfire.config import LogfireConfig
from logfire.testing import IncrementalIdGenerator, TestExporter, TestMetricExporter, TimeGenerator


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
def metric_exporter() -> TestMetricExporter:
    return TestMetricExporter()


@pytest.fixture
def config(
    exporter: TestExporter, id_generator: IncrementalIdGenerator, time_generator: TimeGenerator
) -> LogfireConfig:
    return LogfireConfig.from_processors(
        SimpleSpanProcessor(exporter),
        service_name='logfire-sdk-testing',
        id_generator=id_generator,
        ns_time_generator=time_generator,
    )


@pytest.fixture
def logfire(config: LogfireConfig) -> Logfire:
    return Logfire(config)
