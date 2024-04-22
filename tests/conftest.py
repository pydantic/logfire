# Import this anyio backend early to prevent weird bug caused by concurrent calls to ast.parse
import os
from pathlib import Path

import anyio._backends._asyncio  # noqa  # type: ignore
import pytest
from opentelemetry import trace
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.trace.export import SimpleSpanProcessor

from logfire import configure
from logfire._internal.config import METRICS_PREFERRED_TEMPORALITY
from logfire.testing import IncrementalIdGenerator, TestExporter, TimeGenerator


@pytest.fixture(scope='session', autouse=True)
def anyio_backend():
    return 'asyncio'


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
    return InMemoryMetricReader(preferred_temporality=METRICS_PREFERRED_TEMPORALITY)


@pytest.fixture(autouse=True)
def config(
    exporter: TestExporter,
    metrics_reader: InMemoryMetricReader,
    id_generator: IncrementalIdGenerator,
    time_generator: TimeGenerator,
) -> None:
    configure(
        send_to_logfire=False,
        console=False,
        id_generator=id_generator,
        ns_timestamp_generator=time_generator,
        processors=[SimpleSpanProcessor(exporter)],
        metric_readers=[metrics_reader],
        collect_system_metrics=False,
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


@pytest.fixture
def tmp_dir_cwd(tmp_path: Path):
    """Change the working directory to a temporary directory."""
    cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        yield tmp_path
    finally:
        os.chdir(cwd)


@pytest.fixture
def default_credentials(tmp_path: Path) -> Path:
    auth_file = tmp_path / 'default.toml'
    auth_file.write_text(
        """
        [tokens."https://logfire-api.pydantic.dev"]
        token = "0kYhc414Ys2FNDRdt5vFB05xFx5NjVcbcBMy4Kp6PH0W"
        expiration = "2099-12-31T23:59:59"
        """
    )
    return auth_file
