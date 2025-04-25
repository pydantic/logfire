# Import this anyio backend early to prevent weird bug caused by concurrent calls to ast.parse
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

import anyio._backends._asyncio  # noqa  # type: ignore
import pytest
from opentelemetry import trace
from opentelemetry.sdk._logs.export import SimpleLogRecordProcessor
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.id_generator import IdGenerator

import logfire
from logfire import configure
from logfire._internal.config import METRICS_PREFERRED_TEMPORALITY
from logfire._internal.exporters.test import TestLogExporter
from logfire.integrations.pydantic import set_pydantic_plugin_config
from logfire.testing import IncrementalIdGenerator, TestExporter, TimeGenerator

# Emit both new and old semantic convention attribute names
os.environ['OTEL_SEMCONV_STABILITY_OPT_IN'] = 'http/dup'

# Ensure that LOGFIRE_TOKEN in the environment doesn't interfere
os.environ['LOGFIRE_TOKEN'] = ''

try:
    from agents.tracing.setup import GLOBAL_TRACE_PROVIDER

    GLOBAL_TRACE_PROVIDER.shutdown()
    GLOBAL_TRACE_PROVIDER.set_processors([])
except ImportError:
    pass


@pytest.fixture(scope='session', autouse=True)
def anyio_backend():
    return 'asyncio'


@pytest.fixture(autouse=True)
def reset_pydantic_plugin_config():
    set_pydantic_plugin_config(None)


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


@pytest.fixture
def logs_exporter(time_generator: TimeGenerator) -> TestLogExporter:
    return TestLogExporter(time_generator)


@pytest.fixture
def config_kwargs(
    exporter: TestExporter,
    logs_exporter: TestLogExporter,
    id_generator: IdGenerator,
    time_generator: TimeGenerator,
) -> dict[str, Any]:
    """
    Use this when you want to `logfire.configure()` with a variation of the default configuration.

    Note that this doesn't set `additional_metric_readers` because `metrics_reader` can't be used twice.
    """
    return dict(
        send_to_logfire=False,
        console=False,
        advanced=logfire.AdvancedOptions(
            id_generator=id_generator,
            ns_timestamp_generator=time_generator,
            log_record_processors=[SimpleLogRecordProcessor(logs_exporter)],
        ),
        additional_span_processors=[SimpleSpanProcessor(exporter)],
        # Ensure that inspect_arguments doesn't break things in most versions
        # (it's off by default for <3.11) but it's completely forbidden for 3.8.
        inspect_arguments=sys.version_info[:2] >= (3, 9),
        distributed_tracing=True,
    )


@pytest.fixture(autouse=True)
def config(config_kwargs: dict[str, Any], metrics_reader: InMemoryMetricReader) -> None:
    configure(
        **config_kwargs,
        metrics=logfire.MetricsOptions(
            additional_readers=[metrics_reader],
        ),
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
        [tokens."https://logfire-us.pydantic.dev"]
        token = "pylf_v1_us_0kYhc414Ys2FNDRdt5vFB05xFx5NjVcbcBMy4Kp6PH0W"
        expiration = "2099-12-31T23:59:59"
        """
    )
    return auth_file


@pytest.fixture
def expired_credentials(tmp_path: Path) -> Path:
    auth_file = tmp_path / 'default.toml'
    auth_file.write_text(
        """
        [tokens."https://logfire-us.pydantic.dev"]
        token = "pylf_v1_us_0kYhc414Ys2FNDRdt5vFB05xFx5NjVcbcBMy4Kp6PH0W"
        expiration = "1970-01-01T00:00:00"
        """
    )
    return auth_file


@pytest.fixture
def multiple_credentials(tmp_path: Path) -> Path:
    auth_file = tmp_path / 'default.toml'
    auth_file.write_text(
        """
        [tokens."https://logfire-us.pydantic.dev"]
        token = "pylf_v1_us_0kYhc414Ys2FNDRdt5vFB05xFx5NjVcbcBMy4Kp6PH0W"
        expiration = "2099-12-31T23:59:59"
        [tokens."https://logfire-eu.pydantic.dev"]
        token = "pylf_v1_eu_0kYhc414Ys2FNDRdt5vFB05xFx5NjVcbcBMy4Kp6PH0W"
        expiration = "2099-12-31T23:59:59"
        """
    )
    return auth_file


@pytest.fixture(scope='module')
def vcr_config():
    return {'filter_headers': ['authorization', 'cookie', 'Set-Cookie']}
