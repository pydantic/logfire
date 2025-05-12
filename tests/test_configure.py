from __future__ import annotations

import dataclasses
import json
import os
import sys
import threading
from contextlib import ExitStack
from pathlib import Path
from time import sleep, time
from typing import Any, Iterable, Sequence
from unittest import mock
from unittest.mock import call, patch

import inline_snapshot.extra
import pytest
import requests.exceptions
import requests_mock
from dirty_equals import IsStr
from inline_snapshot import snapshot
from opentelemetry._logs import get_logger_provider
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.metrics import NoOpMeterProvider, get_meter_provider
from opentelemetry.propagate import get_global_textmap
from opentelemetry.propagators.composite import CompositePropagator
from opentelemetry.sdk._logs import LogRecordProcessor
from opentelemetry.sdk._logs._internal import SynchronousMultiLogRecordProcessor
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor, SimpleLogRecordProcessor
from opentelemetry.sdk.metrics.export import InMemoryMetricReader, PeriodicExportingMetricReader
from opentelemetry.sdk.trace import ReadableSpan, SpanProcessor, SynchronousMultiSpanProcessor
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    ConsoleSpanExporter,
    SimpleSpanProcessor,
    SpanExporter,
    SpanExportResult,
)
from opentelemetry.trace import get_tracer_provider
from pydantic import __version__ as pydantic_version
from pytest import LogCaptureFixture

import logfire
from logfire import configure, propagate
from logfire._internal.config import (
    GLOBAL_CONFIG,
    CodeSource,
    ConsoleOptions,
    LogfireConfig,
    LogfireCredentials,
    _get_token_repr,  # type: ignore
    get_base_url_from_token,
    sanitize_project_name,
)
from logfire._internal.exporters.console import ConsoleLogExporter, ShowParentsConsoleSpanExporter
from logfire._internal.exporters.dynamic_batch import DynamicBatchSpanProcessor
from logfire._internal.exporters.logs import CheckSuppressInstrumentationLogProcessorWrapper, MainLogProcessorWrapper
from logfire._internal.exporters.otlp import QuietLogExporter, QuietSpanExporter
from logfire._internal.exporters.processor_wrapper import (
    CheckSuppressInstrumentationProcessorWrapper,
    MainSpanProcessorWrapper,
)
from logfire._internal.exporters.quiet_metrics import QuietMetricExporter
from logfire._internal.exporters.remove_pending import RemovePendingSpansExporter
from logfire._internal.integrations.executors import deserialize_config, serialize_config
from logfire._internal.tracer import PendingSpanProcessor
from logfire._internal.utils import SeededRandomIdGenerator, get_version
from logfire.exceptions import LogfireConfigError
from logfire.integrations.pydantic import get_pydantic_plugin_config
from logfire.propagate import NoExtractTraceContextPropagator, WarnOnExtractTraceContextPropagator
from logfire.testing import TestExporter

PROCESS_RUNTIME_VERSION_REGEX = r'(?P<major>\d+)\.(?P<minor>\d+)\.(?P<patch>\d+)'


@pytest.fixture(autouse=True)
def no_log_on_config(config: None, caplog: pytest.LogCaptureFixture) -> None:
    assert not caplog.messages


def test_propagate_config_to_tags(exporter: TestExporter) -> None:
    tags1 = logfire.with_tags('tag1', 'tag2')
    tags2 = logfire.with_tags('tag3', 'tag4')

    for lf in (logfire, tags1, tags2):
        with lf.span('root'):
            with lf.span('child'):
                logfire.info('test1')
                tags1.info('test2')
                tags2.info('test3')

    assert exporter.exported_spans_as_dict(_include_pending_spans=True) == snapshot(
        [
            {
                'name': 'root',
                'context': {'trace_id': 1, 'span_id': 2, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 1000000000,
                'end_time': 1000000000,
                'attributes': {
                    'code.filepath': 'test_configure.py',
                    'code.lineno': 123,
                    'code.function': 'test_propagate_config_to_tags',
                    'logfire.msg_template': 'root',
                    'logfire.msg': 'root',
                    'logfire.span_type': 'pending_span',
                    'logfire.pending_parent_id': '0000000000000000',
                },
            },
            {
                'name': 'child',
                'context': {'trace_id': 1, 'span_id': 4, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
                'start_time': 2000000000,
                'end_time': 2000000000,
                'attributes': {
                    'code.filepath': 'test_configure.py',
                    'code.lineno': 123,
                    'code.function': 'test_propagate_config_to_tags',
                    'logfire.msg_template': 'child',
                    'logfire.msg': 'child',
                    'logfire.span_type': 'pending_span',
                    'logfire.pending_parent_id': '0000000000000001',
                },
            },
            {
                'name': 'test1',
                'context': {'trace_id': 1, 'span_id': 5, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
                'start_time': 3000000000,
                'end_time': 3000000000,
                'attributes': {
                    'logfire.span_type': 'log',
                    'logfire.level_num': 9,
                    'logfire.msg_template': 'test1',
                    'logfire.msg': 'test1',
                    'code.filepath': 'test_configure.py',
                    'code.lineno': 123,
                    'code.function': 'test_propagate_config_to_tags',
                },
            },
            {
                'name': 'test2',
                'context': {'trace_id': 1, 'span_id': 6, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
                'start_time': 4000000000,
                'end_time': 4000000000,
                'attributes': {
                    'logfire.span_type': 'log',
                    'logfire.level_num': 9,
                    'logfire.msg_template': 'test2',
                    'logfire.msg': 'test2',
                    'code.filepath': 'test_configure.py',
                    'code.lineno': 123,
                    'code.function': 'test_propagate_config_to_tags',
                    'logfire.tags': ('tag1', 'tag2'),
                },
            },
            {
                'name': 'test3',
                'context': {'trace_id': 1, 'span_id': 7, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
                'start_time': 5000000000,
                'end_time': 5000000000,
                'attributes': {
                    'logfire.span_type': 'log',
                    'logfire.level_num': 9,
                    'logfire.msg_template': 'test3',
                    'logfire.msg': 'test3',
                    'code.filepath': 'test_configure.py',
                    'code.lineno': 123,
                    'code.function': 'test_propagate_config_to_tags',
                    'logfire.tags': ('tag3', 'tag4'),
                },
            },
            {
                'name': 'child',
                'context': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 2000000000,
                'end_time': 6000000000,
                'attributes': {
                    'code.filepath': 'test_configure.py',
                    'code.lineno': 123,
                    'code.function': 'test_propagate_config_to_tags',
                    'logfire.msg_template': 'child',
                    'logfire.span_type': 'span',
                    'logfire.msg': 'child',
                },
            },
            {
                'name': 'root',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 7000000000,
                'attributes': {
                    'code.filepath': 'test_configure.py',
                    'code.lineno': 123,
                    'code.function': 'test_propagate_config_to_tags',
                    'logfire.msg_template': 'root',
                    'logfire.span_type': 'span',
                    'logfire.msg': 'root',
                },
            },
            {
                'name': 'root',
                'context': {'trace_id': 2, 'span_id': 9, 'is_remote': False},
                'parent': {'trace_id': 2, 'span_id': 8, 'is_remote': False},
                'start_time': 8000000000,
                'end_time': 8000000000,
                'attributes': {
                    'code.filepath': 'test_configure.py',
                    'code.lineno': 123,
                    'code.function': 'test_propagate_config_to_tags',
                    'logfire.msg_template': 'root',
                    'logfire.msg': 'root',
                    'logfire.tags': ('tag1', 'tag2'),
                    'logfire.span_type': 'pending_span',
                    'logfire.pending_parent_id': '0000000000000000',
                },
            },
            {
                'name': 'child',
                'context': {'trace_id': 2, 'span_id': 11, 'is_remote': False},
                'parent': {'trace_id': 2, 'span_id': 10, 'is_remote': False},
                'start_time': 9000000000,
                'end_time': 9000000000,
                'attributes': {
                    'code.filepath': 'test_configure.py',
                    'code.lineno': 123,
                    'code.function': 'test_propagate_config_to_tags',
                    'logfire.msg_template': 'child',
                    'logfire.msg': 'child',
                    'logfire.tags': ('tag1', 'tag2'),
                    'logfire.span_type': 'pending_span',
                    'logfire.pending_parent_id': '0000000000000008',
                },
            },
            {
                'name': 'test1',
                'context': {'trace_id': 2, 'span_id': 12, 'is_remote': False},
                'parent': {'trace_id': 2, 'span_id': 10, 'is_remote': False},
                'start_time': 10000000000,
                'end_time': 10000000000,
                'attributes': {
                    'logfire.span_type': 'log',
                    'logfire.level_num': 9,
                    'logfire.msg_template': 'test1',
                    'logfire.msg': 'test1',
                    'code.filepath': 'test_configure.py',
                    'code.lineno': 123,
                    'code.function': 'test_propagate_config_to_tags',
                },
            },
            {
                'name': 'test2',
                'context': {'trace_id': 2, 'span_id': 13, 'is_remote': False},
                'parent': {'trace_id': 2, 'span_id': 10, 'is_remote': False},
                'start_time': 11000000000,
                'end_time': 11000000000,
                'attributes': {
                    'logfire.span_type': 'log',
                    'logfire.level_num': 9,
                    'logfire.msg_template': 'test2',
                    'logfire.msg': 'test2',
                    'code.filepath': 'test_configure.py',
                    'code.lineno': 123,
                    'code.function': 'test_propagate_config_to_tags',
                    'logfire.tags': ('tag1', 'tag2'),
                },
            },
            {
                'name': 'test3',
                'context': {'trace_id': 2, 'span_id': 14, 'is_remote': False},
                'parent': {'trace_id': 2, 'span_id': 10, 'is_remote': False},
                'start_time': 12000000000,
                'end_time': 12000000000,
                'attributes': {
                    'logfire.span_type': 'log',
                    'logfire.level_num': 9,
                    'logfire.msg_template': 'test3',
                    'logfire.msg': 'test3',
                    'code.filepath': 'test_configure.py',
                    'code.lineno': 123,
                    'code.function': 'test_propagate_config_to_tags',
                    'logfire.tags': ('tag3', 'tag4'),
                },
            },
            {
                'name': 'child',
                'context': {'trace_id': 2, 'span_id': 10, 'is_remote': False},
                'parent': {'trace_id': 2, 'span_id': 8, 'is_remote': False},
                'start_time': 9000000000,
                'end_time': 13000000000,
                'attributes': {
                    'code.filepath': 'test_configure.py',
                    'code.lineno': 123,
                    'code.function': 'test_propagate_config_to_tags',
                    'logfire.msg_template': 'child',
                    'logfire.tags': ('tag1', 'tag2'),
                    'logfire.span_type': 'span',
                    'logfire.msg': 'child',
                },
            },
            {
                'name': 'root',
                'context': {'trace_id': 2, 'span_id': 8, 'is_remote': False},
                'parent': None,
                'start_time': 8000000000,
                'end_time': 14000000000,
                'attributes': {
                    'code.filepath': 'test_configure.py',
                    'code.lineno': 123,
                    'code.function': 'test_propagate_config_to_tags',
                    'logfire.msg_template': 'root',
                    'logfire.tags': ('tag1', 'tag2'),
                    'logfire.span_type': 'span',
                    'logfire.msg': 'root',
                },
            },
            {
                'name': 'root',
                'context': {'trace_id': 3, 'span_id': 16, 'is_remote': False},
                'parent': {'trace_id': 3, 'span_id': 15, 'is_remote': False},
                'start_time': 15000000000,
                'end_time': 15000000000,
                'attributes': {
                    'code.filepath': 'test_configure.py',
                    'code.lineno': 123,
                    'code.function': 'test_propagate_config_to_tags',
                    'logfire.msg_template': 'root',
                    'logfire.msg': 'root',
                    'logfire.tags': ('tag3', 'tag4'),
                    'logfire.span_type': 'pending_span',
                    'logfire.pending_parent_id': '0000000000000000',
                },
            },
            {
                'name': 'child',
                'context': {'trace_id': 3, 'span_id': 18, 'is_remote': False},
                'parent': {'trace_id': 3, 'span_id': 17, 'is_remote': False},
                'start_time': 16000000000,
                'end_time': 16000000000,
                'attributes': {
                    'code.filepath': 'test_configure.py',
                    'code.lineno': 123,
                    'code.function': 'test_propagate_config_to_tags',
                    'logfire.msg_template': 'child',
                    'logfire.msg': 'child',
                    'logfire.tags': ('tag3', 'tag4'),
                    'logfire.span_type': 'pending_span',
                    'logfire.pending_parent_id': '000000000000000f',
                },
            },
            {
                'name': 'test1',
                'context': {'trace_id': 3, 'span_id': 19, 'is_remote': False},
                'parent': {'trace_id': 3, 'span_id': 17, 'is_remote': False},
                'start_time': 17000000000,
                'end_time': 17000000000,
                'attributes': {
                    'logfire.span_type': 'log',
                    'logfire.level_num': 9,
                    'logfire.msg_template': 'test1',
                    'logfire.msg': 'test1',
                    'code.filepath': 'test_configure.py',
                    'code.lineno': 123,
                    'code.function': 'test_propagate_config_to_tags',
                },
            },
            {
                'name': 'test2',
                'context': {'trace_id': 3, 'span_id': 20, 'is_remote': False},
                'parent': {'trace_id': 3, 'span_id': 17, 'is_remote': False},
                'start_time': 18000000000,
                'end_time': 18000000000,
                'attributes': {
                    'logfire.span_type': 'log',
                    'logfire.level_num': 9,
                    'logfire.msg_template': 'test2',
                    'logfire.msg': 'test2',
                    'code.filepath': 'test_configure.py',
                    'code.lineno': 123,
                    'code.function': 'test_propagate_config_to_tags',
                    'logfire.tags': ('tag1', 'tag2'),
                },
            },
            {
                'name': 'test3',
                'context': {'trace_id': 3, 'span_id': 21, 'is_remote': False},
                'parent': {'trace_id': 3, 'span_id': 17, 'is_remote': False},
                'start_time': 19000000000,
                'end_time': 19000000000,
                'attributes': {
                    'logfire.span_type': 'log',
                    'logfire.level_num': 9,
                    'logfire.msg_template': 'test3',
                    'logfire.msg': 'test3',
                    'code.filepath': 'test_configure.py',
                    'code.lineno': 123,
                    'code.function': 'test_propagate_config_to_tags',
                    'logfire.tags': ('tag3', 'tag4'),
                },
            },
            {
                'name': 'child',
                'context': {'trace_id': 3, 'span_id': 17, 'is_remote': False},
                'parent': {'trace_id': 3, 'span_id': 15, 'is_remote': False},
                'start_time': 16000000000,
                'end_time': 20000000000,
                'attributes': {
                    'code.filepath': 'test_configure.py',
                    'code.lineno': 123,
                    'code.function': 'test_propagate_config_to_tags',
                    'logfire.msg_template': 'child',
                    'logfire.tags': ('tag3', 'tag4'),
                    'logfire.span_type': 'span',
                    'logfire.msg': 'child',
                },
            },
            {
                'name': 'root',
                'context': {'trace_id': 3, 'span_id': 15, 'is_remote': False},
                'parent': None,
                'start_time': 15000000000,
                'end_time': 21000000000,
                'attributes': {
                    'code.filepath': 'test_configure.py',
                    'code.lineno': 123,
                    'code.function': 'test_propagate_config_to_tags',
                    'logfire.msg_template': 'root',
                    'logfire.tags': ('tag3', 'tag4'),
                    'logfire.span_type': 'span',
                    'logfire.msg': 'root',
                },
            },
        ]
    )


def fresh_pydantic_plugin():
    GLOBAL_CONFIG.param_manager.__dict__.pop('pydantic_plugin', None)  # reset the cached_property
    return get_pydantic_plugin_config()


@pytest.mark.skipif(
    get_version(pydantic_version) < get_version('2.5.0'), reason='skipping for pydantic versions < v2.5'
)
def test_pydantic_plugin_include_exclude_strings():
    logfire.instrument_pydantic(include='inc', exclude='exc')
    assert fresh_pydantic_plugin().include == {'inc'}
    assert fresh_pydantic_plugin().exclude == {'exc'}


def test_deprecated_configure_pydantic_plugin(config_kwargs: dict[str, Any]):
    assert fresh_pydantic_plugin().record == 'off'

    with pytest.warns(UserWarning) as warnings:
        logfire.configure(**config_kwargs, pydantic_plugin=logfire.PydanticPlugin(record='all'))  # type: ignore

    assert fresh_pydantic_plugin().record == 'all'

    assert len(warnings) == 1
    assert str(warnings[0].message) == snapshot(
        'The `pydantic_plugin` argument is deprecated. Use `logfire.instrument_pydantic()` instead.'
    )


def test_read_config_from_environment_variables() -> None:
    assert fresh_pydantic_plugin().record == 'off'

    with patch.dict(os.environ, {'LOGFIRE_PYDANTIC_PLUGIN_RECORD': 'all'}):
        assert fresh_pydantic_plugin().record == 'all'
    with patch.dict(os.environ, {'LOGFIRE_PYDANTIC_PLUGIN_RECORD': 'test'}):
        with pytest.raises(
            LogfireConfigError,
            match="Expected pydantic_plugin_record to be one of \\('off', 'all', 'failure', 'metrics'\\), got 'test'",
        ):
            fresh_pydantic_plugin()

    with patch.dict(os.environ, {'LOGFIRE_SEND_TO_LOGFIRE': 'not-valid'}):
        with inline_snapshot.extra.raises(
            snapshot(
                "LogfireConfigError: Expected send_to_logfire to be an instance of one of (<class 'bool'>, typing.Literal['if-token-present']), got 'not-valid'"
            )
        ):
            configure()

    assert fresh_pydantic_plugin().include == set()
    with patch.dict(os.environ, {'LOGFIRE_PYDANTIC_PLUGIN_INCLUDE': 'test'}):
        assert fresh_pydantic_plugin().include == {'test'}
    with patch.dict(os.environ, {'LOGFIRE_PYDANTIC_PLUGIN_INCLUDE': 'test1, test2'}):
        assert fresh_pydantic_plugin().include == {'test1', 'test2'}

    assert fresh_pydantic_plugin().exclude == set()
    with patch.dict(os.environ, {'LOGFIRE_PYDANTIC_PLUGIN_EXCLUDE': 'test'}):
        assert fresh_pydantic_plugin().exclude == {'test'}
    with patch.dict(os.environ, {'LOGFIRE_PYDANTIC_PLUGIN_EXCLUDE': 'test1, test2'}):
        assert fresh_pydantic_plugin().exclude == {'test1', 'test2'}


def test_read_config_from_pyproject_toml(tmp_path: Path) -> None:
    (tmp_path / 'pyproject.toml').write_text(
        f"""
        [tool.logfire]
        base_url = "https://api.logfire.io"
        send_to_logfire = false
        project_name = "test"
        console_colors = "never"
        console_include_timestamp = false
        console_include_tags = false
        data_dir = "{tmp_path}"
        pydantic_plugin_record = "metrics"
        pydantic_plugin_include = " test1, test2"
        pydantic_plugin_exclude = "test3 ,test4"
        trace_sample_rate = "0.123"
        """
    )

    configure(config_dir=tmp_path)

    assert GLOBAL_CONFIG.advanced.base_url == 'https://api.logfire.io'
    assert GLOBAL_CONFIG.send_to_logfire is False
    assert GLOBAL_CONFIG.console
    assert GLOBAL_CONFIG.console.colors == 'never'
    assert GLOBAL_CONFIG.console.include_timestamps is False
    assert GLOBAL_CONFIG.console.include_tags is False
    assert GLOBAL_CONFIG.data_dir == tmp_path
    assert fresh_pydantic_plugin().record == 'metrics'
    assert fresh_pydantic_plugin().include == {'test1', 'test2'}
    assert fresh_pydantic_plugin().exclude == {'test3', 'test4'}
    assert GLOBAL_CONFIG.sampling.head == 0.123


def test_logfire_invalid_config_dir(tmp_path: Path):
    (tmp_path / 'pyproject.toml').write_text('invalid-data')
    with pytest.raises(
        LogfireConfigError,
        match='Invalid config file:',
    ):
        LogfireConfig(config_dir=tmp_path)


def test_logfire_config_console_options() -> None:
    assert LogfireConfig().console == ConsoleOptions()
    assert LogfireConfig(console=False).console is False
    assert LogfireConfig(console=ConsoleOptions(colors='never', verbose=True)).console == ConsoleOptions(
        colors='never', verbose=True
    )

    with patch.dict(os.environ, {'LOGFIRE_CONSOLE': 'false'}):
        assert LogfireConfig().console is False
    with patch.dict(os.environ, {'LOGFIRE_CONSOLE': 'true'}):
        assert LogfireConfig().console == ConsoleOptions(
            colors='auto', span_style='show-parents', include_timestamps=True, verbose=False
        )
    with patch.dict(os.environ, {'LOGFIRE_CONSOLE_COLORS': 'never'}):
        assert LogfireConfig().console == ConsoleOptions(colors='never')
    with patch.dict(os.environ, {'LOGFIRE_CONSOLE_COLORS': 'test'}):
        with pytest.raises(
            LogfireConfigError,
            match="Expected console_colors to be one of \\('auto', 'always', 'never'\\), got 'test'",
        ):
            LogfireConfig()

    with patch.dict(os.environ, {'LOGFIRE_CONSOLE_VERBOSE': '1'}):
        assert LogfireConfig().console == ConsoleOptions(verbose=True)
    with patch.dict(os.environ, {'LOGFIRE_CONSOLE_VERBOSE': 'false'}):
        assert LogfireConfig().console == ConsoleOptions(verbose=False)


def test_configure_export_delay() -> None:
    class TrackingExporter(SpanExporter):
        def __init__(self) -> None:
            self.last_export_timestamp: float | None = None
            self.export_delays: list[float] = []

        def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
            t = time()
            if self.last_export_timestamp is not None:
                self.export_delays.append(t - self.last_export_timestamp)
            self.last_export_timestamp = t
            return SpanExportResult.SUCCESS

    def configure_tracking_exporter():
        request_mocker = requests_mock.Mocker()
        request_mocker.get(
            'https://logfire-us.pydantic.dev/v1/info',
            json={'project_name': 'myproject', 'project_url': 'fake_project_url'},
        )

        with request_mocker:
            logfire.configure(
                send_to_logfire=True,
                token='abc1',
                console=False,
            )
            wait_for_check_token_thread()

        dynamic_batch_span_processor, *_ = get_span_processors()
        assert isinstance(dynamic_batch_span_processor, DynamicBatchSpanProcessor)
        batch_span_processor = dynamic_batch_span_processor.processor
        assert isinstance(batch_span_processor, BatchSpanProcessor)

        batch_span_processor.span_exporter = TrackingExporter()
        return batch_span_processor.span_exporter

    def check_delays(exp: TrackingExporter, min_delay: float, max_delay: float) -> None:
        for delay in exp.export_delays:
            assert min_delay < delay < max_delay, f'delay was {delay}, which is not between {min_delay} and {max_delay}'

    # test the default behaviour
    exporter = configure_tracking_exporter()
    for _ in range(10):
        logfire.info('test')
    sleep(0.1)
    # Initially the delay is 100 ms
    check_delays(exporter, 0.1, 0.4)

    exporter.export_delays.clear()
    while not exporter.export_delays:
        with logfire.span('test'):
            pass
        sleep(0.1)
    # After the first 10 spans, we increase to 500ms by default
    check_delays(exporter, 0.4, 1.0)

    # test a very small value
    with patch.dict(os.environ, {'OTEL_BSP_SCHEDULE_DELAY': '1'}):
        exporter = configure_tracking_exporter()

    while not exporter.export_delays:
        with logfire.span('test'):
            pass
        sleep(0.03)
    check_delays(exporter, 0.0, 0.1)  # since we set 1ms it should be a very short delay


def test_configure_service_version(tmp_path: str) -> None:
    request_mocker = requests_mock.Mocker()
    request_mocker.get(
        'https://logfire-api.pydantic.dev/v1/info',
        json={'project_name': 'myproject', 'project_url': 'fake_project_url'},
    )

    import subprocess

    git_sha = subprocess.check_output(['git', 'rev-parse', 'HEAD']).decode('ascii').strip()

    with request_mocker:
        configure(token='abc2', service_version='1.2.3')

        assert GLOBAL_CONFIG.service_version == '1.2.3'

        configure(token='abc3')

        assert GLOBAL_CONFIG.service_version == git_sha

        dir = os.getcwd()

        try:
            os.chdir(tmp_path)
            configure(token='abc4')
            assert GLOBAL_CONFIG.service_version is None
        finally:
            os.chdir(dir)

        wait_for_check_token_thread()


def test_otel_service_name_env_var(config_kwargs: dict[str, Any], exporter: TestExporter) -> None:
    with patch.dict(os.environ, {'OTEL_SERVICE_NAME': 'potato'}):
        configure(service_version='1.2.3', **config_kwargs)

    logfire.info('test1')

    assert exporter.exported_spans_as_dict(include_resources=True) == snapshot(
        [
            {
                'name': 'test1',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 1000000000,
                'attributes': {
                    'logfire.span_type': 'log',
                    'logfire.level_num': 9,
                    'logfire.msg_template': 'test1',
                    'logfire.msg': 'test1',
                    'code.filepath': 'test_configure.py',
                    'code.function': 'test_otel_service_name_env_var',
                    'code.lineno': 123,
                },
                'resource': {
                    'attributes': {
                        'telemetry.sdk.language': 'python',
                        'telemetry.sdk.name': 'opentelemetry',
                        'telemetry.sdk.version': '0.0.0',
                        'service.name': 'potato',
                        'service.version': '1.2.3',
                        'service.instance.id': '00000000000000000000000000000000',
                        'process.runtime.name': 'cpython',
                        'process.runtime.version': IsStr(regex=PROCESS_RUNTIME_VERSION_REGEX),
                        'process.runtime.description': sys.version,
                        'process.pid': 1234,
                    }
                },
            }
        ]
    )


def test_otel_otel_resource_attributes_env_var(config_kwargs: dict[str, Any], exporter: TestExporter) -> None:
    with patch.dict(
        os.environ,
        {'OTEL_RESOURCE_ATTRIBUTES': 'service.name=banana,service.version=1.2.3,service.instance.id=instance_id'},
    ):
        configure(**config_kwargs)

    logfire.info('test1')

    assert exporter.exported_spans_as_dict(include_resources=True) == snapshot(
        [
            {
                'name': 'test1',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 1000000000,
                'attributes': {
                    'logfire.span_type': 'log',
                    'logfire.level_num': 9,
                    'logfire.msg_template': 'test1',
                    'logfire.msg': 'test1',
                    'code.filepath': 'test_configure.py',
                    'code.function': 'test_otel_otel_resource_attributes_env_var',
                    'code.lineno': 123,
                },
                'resource': {
                    'attributes': {
                        'telemetry.sdk.language': 'python',
                        'telemetry.sdk.name': 'opentelemetry',
                        'telemetry.sdk.version': '0.0.0',
                        'service.name': 'banana',
                        'service.version': '1.2.3',
                        'service.instance.id': 'instance_id',
                        'process.pid': 1234,
                        'process.runtime.name': 'cpython',
                        'process.runtime.version': IsStr(regex=PROCESS_RUNTIME_VERSION_REGEX),
                        'process.runtime.description': sys.version,
                    }
                },
            }
        ]
    )


def test_otel_service_name_has_priority_on_otel_resource_attributes_service_name_env_var(
    config_kwargs: dict[str, Any], exporter: TestExporter
) -> None:
    with patch.dict(
        os.environ,
        dict(OTEL_SERVICE_NAME='potato', OTEL_RESOURCE_ATTRIBUTES='service.name=banana,service.version=1.2.3'),
    ):
        configure(**config_kwargs)

    logfire.info('test1')

    assert exporter.exported_spans_as_dict(include_resources=True) == snapshot(
        [
            {
                'name': 'test1',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 1000000000,
                'attributes': {
                    'logfire.span_type': 'log',
                    'logfire.level_num': 9,
                    'logfire.msg_template': 'test1',
                    'logfire.msg': 'test1',
                    'code.filepath': 'test_configure.py',
                    'code.function': 'test_otel_service_name_has_priority_on_otel_resource_attributes_service_name_env_var',
                    'code.lineno': 123,
                },
                'resource': {
                    'attributes': {
                        'telemetry.sdk.language': 'python',
                        'telemetry.sdk.name': 'opentelemetry',
                        'telemetry.sdk.version': '0.0.0',
                        'service.name': 'banana',
                        'service.version': '1.2.3',
                        'service.instance.id': '00000000000000000000000000000000',
                        'process.pid': 1234,
                        'process.runtime.name': 'cpython',
                        'process.runtime.version': IsStr(regex=PROCESS_RUNTIME_VERSION_REGEX),
                        'process.runtime.description': sys.version,
                    }
                },
            }
        ]
    )


def test_config_serializable():
    """
    Tests that by default, the logfire config can be serialized in the way that we do when sending it to another process.

    Here's an example of a configuration that (as of writing) fails to serialize:

        from opentelemetry.sdk.trace.export import SimpleSpanProcessor

        import logfire
        from logfire._internal.exporters.console import SimpleConsoleSpanExporter
        from logfire._internal.integrations.executors import serialize_config

        logfire.configure(additional_span_processors=[SimpleSpanProcessor(SimpleConsoleSpanExporter())])

        serialize_config()  # fails because SimpleConsoleSpanExporter contains sys.stdout

    This implies that the default processors cannot be stored in the config alongside user-defined processors.

    In particular we also need to check that config values that are dataclasses are handled properly:
    they get serialized to dicts (which dataclasses.asdict does automatically),
    and deserialized back to dataclasses (which we have to do manually).
    """
    logfire.configure(
        send_to_logfire=False,
        console=logfire.ConsoleOptions(verbose=True),
        sampling=logfire.SamplingOptions(),
        scrubbing=logfire.ScrubbingOptions(),
        code_source=logfire.CodeSource(repository='https://github.com/pydantic/logfire', revision='main'),
    )

    for field in dataclasses.fields(GLOBAL_CONFIG):
        # Check that the full set of dataclass fields is known.
        # If a new field appears here, make sure it gets deserialized properly in configure, and tested here.
        assert dataclasses.is_dataclass(getattr(GLOBAL_CONFIG, field.name)) == (
            field.name in ['console', 'sampling', 'scrubbing', 'advanced', 'code_source']
        )

    serialized = serialize_config()
    GLOBAL_CONFIG._initialized = False  # type: ignore  # ensure deserialize_config actually configures
    deserialize_config(serialized)
    serialized2 = serialize_config()

    def normalize(s: dict[str, Any]) -> dict[str, Any]:
        for value in s.values():
            assert not dataclasses.is_dataclass(value)
        return s

    assert normalize(serialized) == normalize(serialized2)

    assert isinstance(GLOBAL_CONFIG.console, logfire.ConsoleOptions)
    assert isinstance(GLOBAL_CONFIG.sampling, logfire.SamplingOptions)
    assert isinstance(GLOBAL_CONFIG.scrubbing, logfire.ScrubbingOptions)
    assert isinstance(GLOBAL_CONFIG.advanced, logfire.AdvancedOptions)
    assert isinstance(GLOBAL_CONFIG.advanced.id_generator, SeededRandomIdGenerator)


def test_config_serializable_console_false():
    logfire.configure(send_to_logfire=False, console=False)
    assert GLOBAL_CONFIG.console is False

    deserialize_config(serialize_config())
    assert GLOBAL_CONFIG.console is False


def test_sanitize_project_name():
    assert sanitize_project_name('foo') == 'foo'
    assert sanitize_project_name('FOO') == 'foo'
    assert sanitize_project_name('  foo - bar!!') == 'foobar'
    assert sanitize_project_name('  Foo - BAR!!') == 'foobar'
    assert sanitize_project_name('') == 'untitled'
    assert sanitize_project_name('-') == 'untitled'
    assert sanitize_project_name('...') == 'untitled'
    long_name = 'abcdefg' * 20
    assert sanitize_project_name(long_name) == long_name[:41]


def test_initialize_project_use_existing_project_no_projects(tmp_dir_cwd: Path, tmp_path: Path):
    auth_file = tmp_path / 'default.toml'
    auth_file.write_text(
        '[tokens."https://logfire-api.pydantic.dev"]\ntoken = "fake_user_token"\nexpiration = "2099-12-31T23:59:59"'
    )
    with ExitStack() as stack:
        stack.enter_context(mock.patch('logfire._internal.config.DEFAULT_FILE', auth_file))
        confirm_mock = stack.enter_context(mock.patch('rich.prompt.Confirm.ask', side_effect=[True, True]))
        stack.enter_context(mock.patch('rich.prompt.Prompt.ask', side_effect=['', 'myproject', '']))

        request_mocker = requests_mock.Mocker()
        stack.enter_context(request_mocker)
        request_mocker.get('https://logfire-api.pydantic.dev/v1/projects/', json=[])
        request_mocker.get(
            'https://logfire-api.pydantic.dev/v1/organizations/', json=[{'organization_name': 'fake_org'}]
        )
        request_mocker.get(
            'https://logfire-api.pydantic.dev/v1/info',
            json={'project_name': 'myproject', 'project_url': 'fake_project_url'},
        )
        create_project_response = {
            'json': {
                'project_name': 'myproject',
                'token': 'fake_token',
                'project_url': 'fake_project_url',
            }
        }
        request_mocker.post('https://logfire-api.pydantic.dev/v1/projects/fake_org', [create_project_response])

        logfire.configure(send_to_logfire=True)
        wait_for_check_token_thread()

        assert confirm_mock.mock_calls == [
            call('The project will be created in the organization "fake_org". Continue?', default=True),
        ]


def test_initialize_project_use_existing_project(tmp_dir_cwd: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    auth_file = tmp_path / 'default.toml'
    auth_file.write_text(
        '[tokens."https://logfire-api.pydantic.dev"]\ntoken = "fake_user_token"\nexpiration = "2099-12-31T23:59:59"'
    )
    with ExitStack() as stack:
        stack.enter_context(mock.patch('logfire._internal.config.DEFAULT_FILE', auth_file))
        confirm_mock = stack.enter_context(mock.patch('rich.prompt.Confirm.ask', side_effect=[True, True]))
        prompt_mock = stack.enter_context(mock.patch('rich.prompt.Prompt.ask', side_effect=['1', '']))

        request_mocker = requests_mock.Mocker()
        stack.enter_context(request_mocker)
        request_mocker.get(
            'https://logfire-api.pydantic.dev/v1/projects/',
            json=[{'organization_name': 'fake_org', 'project_name': 'fake_project'}],
        )
        request_mocker.get(
            'https://logfire-api.pydantic.dev/v1/info',
            json={'project_name': 'myproject', 'project_url': 'fake_project_url'},
        )
        create_project_response = {
            'json': {
                'project_name': 'myproject',
                'token': 'fake_token',
                'project_url': 'fake_project_url',
            }
        }
        request_mocker.post(
            'https://logfire-api.pydantic.dev/v1/organizations/fake_org/projects/fake_project/write-tokens/',
            [create_project_response],
        )

        logfire.configure(send_to_logfire=True)

        assert confirm_mock.mock_calls == [
            call('Do you want to use one of your existing projects? ', default=True),
        ]
        assert prompt_mock.mock_calls == [
            call(
                'Please select one of the following projects by number:\n1. fake_org/fake_project\n',
                choices=['1'],
                default='1',
            ),
            call(
                'Project initialized successfully. You will be able to view it at: fake_project_url\nPress Enter to continue',
            ),
        ]
        wait_for_check_token_thread()
        assert capsys.readouterr().err == 'Logfire project URL: fake_project_url\n'

        assert json.loads((tmp_dir_cwd / '.logfire/logfire_credentials.json').read_text()) == {
            **create_project_response['json'],
            'logfire_api_url': 'https://logfire-api.pydantic.dev',
        }


def test_initialize_project_not_using_existing_project(
    tmp_dir_cwd: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    auth_file = tmp_path / 'default.toml'
    auth_file.write_text(
        '[tokens."https://logfire-api.pydantic.dev"]\ntoken = "fake_user_token"\nexpiration = "2099-12-31T23:59:59"'
    )
    with ExitStack() as stack:
        stack.enter_context(mock.patch('logfire._internal.config.DEFAULT_FILE', auth_file))
        confirm_mock = stack.enter_context(mock.patch('rich.prompt.Confirm.ask', side_effect=[False, True]))
        prompt_mock = stack.enter_context(mock.patch('rich.prompt.Prompt.ask', side_effect=['my-project', '']))

        request_mocker = requests_mock.Mocker()
        stack.enter_context(request_mocker)
        request_mocker.get(
            'https://logfire-api.pydantic.dev/v1/organizations/', json=[{'organization_name': 'fake_org'}]
        )
        request_mocker.get(
            'https://logfire-api.pydantic.dev/v1/info',
            json={'project_name': 'myproject', 'project_url': 'fake_project_url'},
        )
        request_mocker.get(
            'https://logfire-api.pydantic.dev/v1/projects/',
            json=[{'organization_name': 'fake_org', 'project_name': 'fake_project'}],
        )
        create_project_response = {
            'json': {
                'project_name': 'myproject',
                'token': 'fake_token',
                'project_url': 'fake_project_url',
            }
        }
        request_mocker.post('https://logfire-api.pydantic.dev/v1/projects/fake_org', [create_project_response])
        request_mocker.post(
            'https://logfire-api.pydantic.dev/v1/organizations/fake_org/projects/fake_project/write-tokens/',
            [create_project_response],
        )

        logfire.configure(send_to_logfire=True)

        assert confirm_mock.mock_calls == [
            call('Do you want to use one of your existing projects? ', default=True),
            call('The project will be created in the organization "fake_org". Continue?', default=True),
        ]
        assert prompt_mock.mock_calls == [
            call('Enter the project name', default='testinitializeprojectnotus0'),
            call(
                'Project initialized successfully. You will be able to view it at: fake_project_url\nPress Enter to continue'
            ),
        ]
        wait_for_check_token_thread()
        assert capsys.readouterr().err == 'Logfire project URL: fake_project_url\n'

        assert json.loads((tmp_dir_cwd / '.logfire/logfire_credentials.json').read_text()) == {
            **create_project_response['json'],
            'logfire_api_url': 'https://logfire-api.pydantic.dev',
        }


def test_initialize_project_not_confirming_organization(tmp_path: Path) -> None:
    auth_file = tmp_path / 'default.toml'
    auth_file.write_text(
        '[tokens."https://logfire-api.pydantic.dev"]\ntoken = "fake_user_token"\nexpiration = "2099-12-31T23:59:59"'
    )
    with ExitStack() as stack:
        stack.enter_context(mock.patch('logfire._internal.config.DEFAULT_FILE', auth_file))
        confirm_mock = stack.enter_context(mock.patch('rich.prompt.Confirm.ask', side_effect=[False, False]))

        request_mocker = requests_mock.Mocker()
        stack.enter_context(request_mocker)
        request_mocker.get(
            'https://logfire-api.pydantic.dev/v1/organizations/', json=[{'organization_name': 'fake_org'}]
        )
        request_mocker.get(
            'https://logfire-api.pydantic.dev/v1/projects/',
            json=[{'organization_name': 'fake_org', 'project_name': 'fake_project'}],
        )

        with pytest.raises(SystemExit):
            logfire.configure(data_dir=tmp_path, send_to_logfire=True)
        wait_for_check_token_thread()

        assert confirm_mock.mock_calls == [
            call('Do you want to use one of your existing projects? ', default=True),
            call('The project will be created in the organization "fake_org". Continue?', default=True),
        ]


@pytest.mark.xdist_group(name='sequential')
def test_initialize_project_create_project(tmp_dir_cwd: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    auth_file = tmp_path / 'default.toml'
    auth_file.write_text(
        '[tokens."https://logfire-api.pydantic.dev"]\ntoken = "fake_user_token"\nexpiration = "2099-12-31T23:59:59"'
    )
    with ExitStack() as stack:
        stack.enter_context(mock.patch('logfire._internal.config.DEFAULT_FILE', auth_file))
        confirm_mock = stack.enter_context(mock.patch('rich.prompt.Confirm.ask', side_effect=[True, True]))
        prompt_mock = stack.enter_context(
            mock.patch(
                'rich.prompt.Prompt.ask',
                side_effect=[
                    'invalid project name',
                    'existingprojectname',
                    'reserved',
                    'myproject',
                    '',
                ],
            )
        )

        request_mocker = requests_mock.Mocker()
        stack.enter_context(request_mocker)
        request_mocker.get('https://logfire-api.pydantic.dev/v1/projects/', json=[])
        request_mocker.get(
            'https://logfire-api.pydantic.dev/v1/organizations/', json=[{'organization_name': 'fake_org'}]
        )
        request_mocker.get(
            'https://logfire-api.pydantic.dev/v1/info',
            json={'project_name': 'myproject', 'project_url': 'fake_project_url'},
        )

        create_existing_project_request_json = {
            'project_name': 'existingprojectname',
        }
        create_existing_project_response = {
            'status_code': 409,
        }

        create_reserved_project_request_json = {
            'project_name': 'reserved',
        }
        create_reserved_project_response = {
            'status_code': 422,
            'json': {
                'detail': [
                    {
                        'loc': ['body', 'project_name'],
                        'msg': 'This project name is reserved and cannot be used.',
                    }
                ],
            },
        }

        create_project_request_json = {
            'project_name': 'myproject',
        }
        create_project_response = {
            'json': {
                'project_name': 'myproject',
                'token': 'fake_token',
                'project_url': 'fake_project_url',
            }
        }
        request_mocker.post(
            'https://logfire-api.pydantic.dev/v1/projects/fake_org',
            [
                create_existing_project_response,
                create_reserved_project_response,
                create_project_response,
            ],
        )

        logfire.configure(send_to_logfire=True)

        for request in request_mocker.request_history[:-1]:
            assert request.headers['Authorization'] == 'fake_user_token'

        # we check that fake_token is valid now when we configure the project
        wait_for_check_token_thread()
        assert request_mocker.request_history[-1].headers['Authorization'] == 'fake_token'

        assert request_mocker.request_history[2].json() == create_existing_project_request_json
        assert request_mocker.request_history[3].json() == create_reserved_project_request_json
        assert request_mocker.request_history[4].json() == create_project_request_json

        assert confirm_mock.mock_calls == [
            call('The project will be created in the organization "fake_org". Continue?', default=True),
        ]
        assert prompt_mock.mock_calls == [
            call(
                'Enter the project name',
                default='testinitializeprojectcreate0',
            ),
            call(
                "\nThe project name you've entered is invalid. Valid project names:\n"
                '  * may contain lowercase alphanumeric characters\n'
                '  * may contain single hyphens\n'
                '  * may not start or end with a hyphen\n\n'
                'Enter the project name you want to use:',
                default='testinitializeprojectcreate0',
            ),
            call(
                "\nA project with the name 'existingprojectname' already exists. Please enter a different project name",
                default=...,
            ),
            call(
                '\nThe project name you entered is invalid:\n'
                'This project name is reserved and cannot be used.\n'
                'Please enter a different project name',
                default=...,
            ),
            call(
                'Project initialized successfully. You will be able to view it at: fake_project_url\nPress Enter to continue',
            ),
        ]
        assert capsys.readouterr().err == 'Logfire project URL: fake_project_url\n'

        assert json.loads((tmp_dir_cwd / '.logfire/logfire_credentials.json').read_text()) == {
            **create_project_response['json'],
            'logfire_api_url': 'https://logfire-api.pydantic.dev',
        }


@pytest.mark.xdist_group(name='sequential')
def test_initialize_project_create_project_default_organization(tmp_dir_cwd: Path, tmp_path: Path):
    auth_file = tmp_path / 'default.toml'
    auth_file.write_text(
        '[tokens."https://logfire-api.pydantic.dev"]\ntoken = "fake_user_token"\nexpiration = "2099-12-31T23:59:59"'
    )
    with ExitStack() as stack:
        stack.enter_context(mock.patch('logfire._internal.config.DEFAULT_FILE', auth_file))
        prompt_mock = stack.enter_context(
            mock.patch('rich.prompt.Prompt.ask', side_effect=['fake_org', 'mytestproject1', ''])
        )

        request_mocker = requests_mock.Mocker()
        stack.enter_context(request_mocker)
        # request_mocker.get('https://logfire-api.pydantic.dev/v1/info', json={'project_name': 'myproject'})
        request_mocker.get('https://logfire-api.pydantic.dev/v1/projects/', json=[])
        request_mocker.get(
            'https://logfire-api.pydantic.dev/v1/organizations/',
            json=[{'organization_name': 'fake_org'}, {'organization_name': 'fake_org1'}],
        )
        request_mocker.get(
            'https://logfire-api.pydantic.dev/v1/info',
            json={'project_name': 'myproject', 'project_url': 'fake_project_url'},
        )
        request_mocker.get(
            'https://logfire-api.pydantic.dev/v1/account/me',
            json={'default_organization': {'organization_name': 'fake_org1'}},
        )

        create_project_response = {
            'json': {
                'project_name': 'myproject',
                'token': 'fake_token',
                'project_url': 'fake_project_url',
            }
        }
        request_mocker.post(
            'https://logfire-api.pydantic.dev/v1/projects/fake_org',
            [create_project_response],
        )

        logfire.configure(send_to_logfire=True)
        wait_for_check_token_thread()

        assert prompt_mock.mock_calls == [
            call(
                '\nTo create and use a new project, please provide the following information:\nSelect the organization to create the project in',
                choices=['fake_org', 'fake_org1'],
                default='fake_org1',
            ),
            call('Enter the project name', default='testinitializeprojectcreate1'),
            call(
                'Project initialized successfully. You will be able to view it at: fake_project_url\nPress Enter to continue'
            ),
        ]


def test_send_to_logfire_true(tmp_path: Path) -> None:
    """
    Test that with send_to_logfire=True, the logic is triggered to ask about creating a project.
    """
    data_dir = tmp_path / 'logfire_data'
    auth_file = tmp_path / 'default.toml'
    auth_file.write_text(
        '[tokens."https://logfire-api.pydantic.dev"]\ntoken = "fake_user_token"\nexpiration = "2099-12-31T23:59:59"'
    )
    with ExitStack() as stack:
        stack.enter_context(mock.patch('logfire._internal.config.DEFAULT_FILE', auth_file))
        stack.enter_context(
            mock.patch(
                'logfire._internal.config.LogfireCredentials.get_user_projects', side_effect=RuntimeError('expected')
            )
        )
        with pytest.raises(RuntimeError, match='^expected$'):
            configure(send_to_logfire=True, console=False, data_dir=data_dir)
    wait_for_check_token_thread()


def test_send_to_logfire_false() -> None:
    """
    Test that with send_to_logfire=False, that logic is NOT triggered.
    """
    with mock.patch('logfire._internal.config.Confirm.ask', side_effect=RuntimeError):
        configure(send_to_logfire=False, console=False)


def test_send_to_logfire_if_token_present() -> None:
    with mock.patch('logfire._internal.config.Confirm.ask', side_effect=RuntimeError):
        with requests_mock.Mocker() as request_mocker:
            configure(send_to_logfire='if-token-present', console=False)
            wait_for_check_token_thread()
            assert GLOBAL_CONFIG.token is None
            assert len(request_mocker.request_history) == 0


def test_send_to_logfire_if_token_present_empty() -> None:
    os.environ['LOGFIRE_TOKEN'] = ''
    try:
        with ExitStack() as stack:
            stack.enter_context(mock.patch('logfire._internal.config.Confirm.ask', side_effect=RuntimeError))
            requests_mocker = stack.enter_context(requests_mock.Mocker())
            configure(send_to_logfire='if-token-present', console=False)
            wait_for_check_token_thread()
            assert len(requests_mocker.request_history) == 0
    finally:
        del os.environ['LOGFIRE_TOKEN']


def test_send_to_logfire_if_token_present_empty_via_env_var() -> None:
    with patch.dict(
        os.environ,
        {'LOGFIRE_TOKEN': '', 'LOGFIRE_SEND_TO_LOGFIRE': 'if-token-present'},
    ), mock.patch(
        'logfire._internal.config.Confirm.ask',
        side_effect=RuntimeError,
    ), requests_mock.Mocker() as requests_mocker:
        configure(console=False)
        wait_for_check_token_thread()
    assert len(requests_mocker.request_history) == 0


def wait_for_check_token_thread():
    for thread in threading.enumerate():
        if thread.name == 'check_logfire_token':  # pragma: no cover
            thread.join()


def test_send_to_logfire_if_token_present_not_empty(capsys: pytest.CaptureFixture[str]) -> None:
    os.environ['LOGFIRE_TOKEN'] = 'foobar'
    try:
        with requests_mock.Mocker() as request_mocker:
            request_mocker.get(
                'https://logfire-us.pydantic.dev/v1/info',
                json={'project_name': 'myproject', 'project_url': 'fake_project_url'},
            )
            configure(send_to_logfire='if-token-present')
            wait_for_check_token_thread()
            assert len(request_mocker.request_history) == 1
            assert capsys.readouterr().err == 'Logfire project URL: fake_project_url\n'
    finally:
        del os.environ['LOGFIRE_TOKEN']


def test_send_to_logfire_if_token_present_in_logfire_dir(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    creds_file = tmp_path / 'logfire_credentials.json'
    creds_file.write_text(
        """
        {
            "token": "foobar",
            "project_name": "myproject",
            "project_url": "https://logfire-us.pydantic.dev",
            "logfire_api_url": "https://logfire-us.pydantic.dev"
        }
        """
    )
    with requests_mock.Mocker() as request_mocker:
        request_mocker.get(
            'https://logfire-us.pydantic.dev/v1/info',
            json={'project_name': 'myproject', 'project_url': 'https://logfire-us.pydantic.dev'},
        )
        configure(send_to_logfire='if-token-present', data_dir=tmp_path)
        wait_for_check_token_thread()
        assert len(request_mocker.request_history) == 1
        assert capsys.readouterr().err == 'Logfire project URL: https://logfire-us.pydantic.dev\n'


def test_configure_unknown_token_region(capsys: pytest.CaptureFixture[str]) -> None:
    # Should default to us:
    with requests_mock.Mocker() as request_mocker:
        request_mocker.get(
            'https://logfire-us.pydantic.dev/v1/info',
            json={'project_name': 'myproject', 'project_url': 'https://logfire-us.pydantic.dev'},
        )
        configure(send_to_logfire='if-token-present', token='pylf_v1_unknownregion_foobarbaz')
        wait_for_check_token_thread()
        assert len(request_mocker.request_history) == 1
        assert capsys.readouterr().err == 'Logfire project URL: https://logfire-us.pydantic.dev\n'


def test_load_creds_file_invalid_json_content(tmp_path: Path):
    creds_file = tmp_path / 'logfire_credentials.json'
    creds_file.write_text('invalid-data')

    with pytest.raises(LogfireConfigError, match='Invalid credentials file:'):
        LogfireCredentials.load_creds_file(creds_dir=tmp_path)


def test_load_creds_file_legacy_key(tmp_path: Path):
    creds_file = tmp_path / 'logfire_credentials.json'
    creds_file.write_text(
        """
        {
            "dashboard_url": "http://dash.localhost:8000/test",
            "token":"test",
            "project_name": "test",
            "logfire_api_url": "http://dash.localhost:8000/"
        }
        """
    )

    cred = LogfireCredentials.load_creds_file(creds_dir=tmp_path)
    assert cred and cred.project_url == 'http://dash.localhost:8000/test'


def test_load_creds_file_invalid_key(tmp_path: Path):
    creds_file = tmp_path / 'logfire_credentials.json'
    creds_file.write_text('{"test": "test"}')

    with pytest.raises(LogfireConfigError, match='Invalid credentials file:'):
        LogfireCredentials.load_creds_file(creds_dir=tmp_path)


def test_get_user_token_data_explicit_url(default_credentials: Path):
    with patch('logfire._internal.config.DEFAULT_FILE', default_credentials):
        # https://logfire-us.pydantic.dev is the URL present in the default credentials fixture:
        _, url = LogfireCredentials._get_user_token_data(logfire_api_url='https://logfire-us.pydantic.dev')  # type: ignore
        assert url == 'https://logfire-us.pydantic.dev'

        with pytest.raises(LogfireConfigError):
            LogfireCredentials._get_user_token_data(logfire_api_url='https://logfire-eu.pydantic.dev')  # type: ignore


def test_get_user_token_data_no_explicit_url(default_credentials: Path):
    with patch('logfire._internal.config.DEFAULT_FILE', default_credentials):
        _, url = LogfireCredentials._get_user_token_data(logfire_api_url=None)  # type: ignore
        # https://logfire-us.pydantic.dev is the URL present in the default credentials fixture:
        assert url == 'https://logfire-us.pydantic.dev'


def test_get_user_token_data_input_choice(multiple_credentials: Path):
    with patch('logfire._internal.config.DEFAULT_FILE', multiple_credentials), patch(
        'rich.prompt.IntPrompt.ask', side_effect=[1]
    ):
        _, url = LogfireCredentials._get_user_token_data(logfire_api_url=None)  # type: ignore
        # https://logfire-us.pydantic.dev is the first URL present in the multiple credentials fixture:
        assert url == 'https://logfire-us.pydantic.dev'


@pytest.mark.parametrize(
    ['url', 'token', 'expected'],
    [
        (
            'https://logfire-us.pydantic.dev',
            'pylf_v1_us_0kYhc414Ys2FNDRdt5vFB05xFx5NjVcbcBMy4Kp6PH0W',
            'US (https://logfire-us.pydantic.dev) - pylf_v1_us_0kYhc****',
        ),
        (
            'https://logfire-eu.pydantic.dev',
            'pylf_v1_eu_0kYhc414Ys2FNDRdt5vFB05xFx5NjVcbcBMy4Kp6PH0W',
            'EU (https://logfire-eu.pydantic.dev) - pylf_v1_eu_0kYhc****',
        ),
        (
            'https://logfire-us.pydantic.dev',
            '0kYhc414Ys2FNDRdt5vFB05xFx5NjVcbcBMy4Kp6PH0W',
            'US (https://logfire-us.pydantic.dev) - 0kYhc****',
        ),
        (
            'https://logfire-us.pydantic.dev',
            'pylf_v1_unknownregion_0kYhc414Ys2FNDRdt5vFB05xFx5NjVcbcBMy4Kp6PH0W',
            'US (https://logfire-us.pydantic.dev) - pylf_v1_unknownregion_0kYhc****',
        ),
    ],
)
def test_get_token_repr(url: str, token: str, expected: str):
    assert _get_token_repr(url, token) == expected


def test_get_user_token_data_no_credentials(tmp_path: Path):
    with patch('logfire._internal.config.DEFAULT_FILE', tmp_path):
        with pytest.raises(LogfireConfigError):
            LogfireCredentials._get_user_token_data()  # type: ignore


def test_get_user_token_data_empty_credentials(tmp_path: Path):
    empty_auth_file = tmp_path / 'default.toml'
    empty_auth_file.touch()
    with patch('logfire._internal.config.DEFAULT_FILE', tmp_path):
        with pytest.raises(LogfireConfigError):
            LogfireCredentials._get_user_token_data()  # type: ignore


def test_get_user_token_data_expired_credentials(expired_credentials: Path):
    with patch('logfire._internal.config.DEFAULT_FILE', expired_credentials):
        with pytest.raises(LogfireConfigError):
            # https://logfire-us.pydantic.dev is the URL present in the expired credentials fixture:
            LogfireCredentials._get_user_token_data(logfire_api_url='https://logfire-us.pydantic.dev')  # type: ignore


def test_get_user_token_data_not_authenticated(default_credentials: Path):
    with patch('logfire._internal.config.DEFAULT_FILE', default_credentials):
        with pytest.raises(
            LogfireConfigError, match='You are not authenticated. Please run `logfire auth` to authenticate.'
        ):
            # Use a port that we don't use for local development to reduce conflicts with local configuration
            LogfireCredentials._get_user_token_data(logfire_api_url='http://localhost:8234')  # type: ignore


def test_initialize_credentials_from_token_unreachable():
    with pytest.warns(
        UserWarning,
        match="Logfire API is unreachable, you may have trouble sending data. Error: Invalid URL '/v1/info': No scheme supplied.",
    ):
        LogfireConfig(advanced=logfire.AdvancedOptions(base_url=''))._initialize_credentials_from_token('some-token')  # type: ignore


def test_initialize_credentials_from_token_invalid_token():
    with ExitStack() as stack:
        request_mocker = requests_mock.Mocker()
        stack.enter_context(request_mocker)
        request_mocker.get(
            'https://logfire-us.pydantic.dev/v1/info', text='{"detail": "Invalid token"}', status_code=401
        )

        with pytest.warns(match='Logfire API returned status code 401. Detail: Invalid token'):
            LogfireConfig()._initialize_credentials_from_token('some-token')  # type: ignore


def test_initialize_credentials_from_token_unhealthy():
    with ExitStack() as stack:
        request_mocker = requests_mock.Mocker()
        stack.enter_context(request_mocker)
        request_mocker.get('https://logfire-us.pydantic.dev/v1/info', text='Error', status_code=500)

        with pytest.warns(
            UserWarning, match='Logfire API returned status code 500, you may have trouble sending data.'
        ):
            LogfireConfig()._initialize_credentials_from_token('some-token')  # type: ignore


def test_configure_twice_no_warning(caplog: LogCaptureFixture):
    logfire.configure(send_to_logfire=False)
    assert not caplog.messages


def test_send_to_logfire_under_pytest():
    """
    Test that the `send_to_logfire` parameter is set to False when running under pytest.
    """
    assert 'PYTEST_VERSION' in os.environ
    logfire.configure()
    assert GLOBAL_CONFIG.send_to_logfire is False


@pytest.mark.skipif(sys.version_info[:2] >= (3, 9), reason='Testing an error only raised in Python 3.8+')
def test_configure_fstring_python_38():
    with pytest.raises(  # pragma: no branch
        LogfireConfigError,
        match=r'Inspecting arguments is only supported in Python 3.9\+ and only recommended in Python 3.11\+.',
    ):
        logfire.configure(send_to_logfire=False, inspect_arguments=True)


def test_default_exporters(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(LogfireConfig, '_initialize_credentials_from_token', lambda *args: None)  # type: ignore
    logfire.configure(send_to_logfire=True, token='foo')
    wait_for_check_token_thread()

    [console_span_processor, send_to_logfire_processor, pending_span_processor] = get_span_processors()

    assert isinstance(console_span_processor, SimpleSpanProcessor)
    assert isinstance(console_span_processor.span_exporter, ShowParentsConsoleSpanExporter)

    assert isinstance(send_to_logfire_processor, DynamicBatchSpanProcessor)
    assert isinstance(send_to_logfire_processor.processor, BatchSpanProcessor)
    assert isinstance(send_to_logfire_processor.processor.span_exporter, RemovePendingSpansExporter)

    assert isinstance(pending_span_processor, PendingSpanProcessor)
    assert isinstance(pending_span_processor.processor, MainSpanProcessorWrapper)
    assert isinstance(pending_span_processor.processor.processor, SynchronousMultiSpanProcessor)
    assert pending_span_processor.processor.processor._span_processors == (  # type: ignore
        console_span_processor,
        send_to_logfire_processor,
    )

    [logfire_metric_reader] = get_metric_readers()
    assert isinstance(logfire_metric_reader, PeriodicExportingMetricReader)
    assert isinstance(logfire_metric_reader._exporter, QuietMetricExporter)  # type: ignore

    [console_log_processor, logfire_log_processor] = get_log_record_processors()

    assert isinstance(console_log_processor, SimpleLogRecordProcessor)
    assert isinstance(console_log_processor._exporter, ConsoleLogExporter)  # type: ignore
    assert console_log_processor._exporter.span_exporter is console_span_processor.span_exporter  # type: ignore

    assert isinstance(logfire_log_processor, BatchLogRecordProcessor)
    assert isinstance(logfire_log_processor._exporter, QuietLogExporter)  # type: ignore
    assert isinstance(logfire_log_processor._exporter.exporter, OTLPLogExporter)  # type: ignore


def test_custom_exporters():
    custom_span_processor = SimpleSpanProcessor(ConsoleSpanExporter())
    custom_metric_reader = InMemoryMetricReader()
    custom_log_processor = SynchronousMultiLogRecordProcessor()

    logfire.configure(
        send_to_logfire=False,
        console=False,
        additional_span_processors=[custom_span_processor],
        metrics=logfire.MetricsOptions(additional_readers=[custom_metric_reader]),
        advanced=logfire.AdvancedOptions(log_record_processors=[custom_log_processor]),
    )

    [custom_span_processor2] = get_span_processors()
    assert custom_span_processor2 is custom_span_processor

    [custom_metric_reader2] = get_metric_readers()
    assert custom_metric_reader2 is custom_metric_reader

    [custom_log_processor2] = get_log_record_processors()
    assert custom_log_processor2 is custom_log_processor


def test_otel_exporter_otlp_endpoint_env_var():
    # Setting this env var creates an OTLPSpanExporter and an OTLPMetricExporter
    with patch.dict(os.environ, {'OTEL_EXPORTER_OTLP_ENDPOINT': 'otel_endpoint'}):
        logfire.configure(send_to_logfire=False, console=False)

    [otel_processor] = get_span_processors()
    assert isinstance(otel_processor, BatchSpanProcessor)
    assert isinstance(otel_processor.span_exporter, OTLPSpanExporter)
    assert otel_processor.span_exporter._endpoint == 'otel_endpoint/v1/traces'  # type: ignore

    [otel_metric_reader] = get_metric_readers()
    assert isinstance(otel_metric_reader, PeriodicExportingMetricReader)
    assert isinstance(otel_metric_reader._exporter, OTLPMetricExporter)  # type: ignore
    assert otel_metric_reader._exporter._endpoint == 'otel_endpoint/v1/metrics'  # type: ignore

    [otel_log_processor] = get_log_record_processors()
    assert isinstance(otel_log_processor, BatchLogRecordProcessor)
    assert isinstance(otel_log_processor._exporter, OTLPLogExporter)  # type: ignore
    assert otel_log_processor._exporter._endpoint == 'otel_endpoint/v1/logs'  # type: ignore


def test_otel_traces_exporter_env_var():
    # Setting OTEL_TRACES_EXPORTER to something other than otlp prevents creating an OTLPSpanExporter
    # Same for OTEL_LOGS_EXPORTER
    with patch.dict(
        os.environ,
        {
            'OTEL_EXPORTER_OTLP_ENDPOINT': 'otel_endpoint2',
            'OTEL_TRACES_EXPORTER': 'grpc',
            'OTEL_LOGS_EXPORTER': 'none',
        },
    ):
        logfire.configure(send_to_logfire=False, console=False)

    assert len(list(get_span_processors())) == 0
    assert len(list(get_log_record_processors())) == 0

    [otel_metric_reader] = get_metric_readers()
    assert isinstance(otel_metric_reader, PeriodicExportingMetricReader)
    assert isinstance(otel_metric_reader._exporter, OTLPMetricExporter)  # type: ignore
    assert otel_metric_reader._exporter._endpoint == 'otel_endpoint2/v1/metrics'  # type: ignore


def test_otel_metrics_exporter_env_var():
    # Setting OTEL_METRICS_EXPORTER to something other than otlp prevents creating an OTLPMetricExporter
    with patch.dict(os.environ, {'OTEL_EXPORTER_OTLP_ENDPOINT': 'otel_endpoint3', 'OTEL_METRICS_EXPORTER': 'none'}):
        logfire.configure(send_to_logfire=False, console=False)

    [otel_processor] = get_span_processors()
    assert isinstance(otel_processor, BatchSpanProcessor)
    assert isinstance(otel_processor.span_exporter, OTLPSpanExporter)
    assert otel_processor.span_exporter._endpoint == 'otel_endpoint3/v1/traces'  # type: ignore

    assert len(list(get_metric_readers())) == 0


def test_otel_logs_exporter_env_var():
    # Setting OTEL_LOGS_EXPORTER to something other than otlp prevents creating an OTLPLogExporter
    with patch.dict(os.environ, {'OTEL_EXPORTER_OTLP_ENDPOINT': 'otel_endpoint4', 'OTEL_LOGS_EXPORTER': 'none'}):
        logfire.configure(send_to_logfire=False, console=False)

    [otel_processor] = get_span_processors()
    assert isinstance(otel_processor, BatchSpanProcessor)
    assert isinstance(otel_processor.span_exporter, OTLPSpanExporter)
    assert otel_processor.span_exporter._endpoint == 'otel_endpoint4/v1/traces'  # type: ignore

    assert len(list(get_log_record_processors())) == 0


def test_otel_exporter_otlp_traces_endpoint_env_var():
    # Setting just OTEL_EXPORTER_OTLP_TRACES_ENDPOINT only creates an OTLPSpanExporter
    with patch.dict(os.environ, {'OTEL_EXPORTER_OTLP_TRACES_ENDPOINT': 'otel_traces_endpoint'}):
        logfire.configure(send_to_logfire=False, console=False)

    [otel_processor] = get_span_processors()
    assert isinstance(otel_processor, BatchSpanProcessor)
    assert isinstance(otel_processor.span_exporter, OTLPSpanExporter)
    assert otel_processor.span_exporter._endpoint == 'otel_traces_endpoint'  # type: ignore

    assert len(list(get_metric_readers())) == 0
    assert len(list(get_log_record_processors())) == 0


def test_otel_exporter_otlp_metrics_endpoint_env_var():
    # Setting just OTEL_EXPORTER_OTLP_METRICS_ENDPOINT only creates an OTLPMetricExporter
    with patch.dict(os.environ, {'OTEL_EXPORTER_OTLP_METRICS_ENDPOINT': 'otel_metrics_endpoint'}):
        logfire.configure(send_to_logfire=False, console=False)

    assert len(list(get_span_processors())) == 0
    assert len(list(get_log_record_processors())) == 0

    [otel_metric_reader] = get_metric_readers()
    assert isinstance(otel_metric_reader, PeriodicExportingMetricReader)
    assert isinstance(otel_metric_reader._exporter, OTLPMetricExporter)  # type: ignore
    assert otel_metric_reader._exporter._endpoint == 'otel_metrics_endpoint'  # type: ignore


def test_otel_exporter_otlp_logs_endpoint_env_var():
    # Setting just OTEL_EXPORTER_OTLP_LOGS_ENDPOINT only creates an OTLPLogExporter
    with patch.dict(os.environ, {'OTEL_EXPORTER_OTLP_LOGS_ENDPOINT': 'otel_logs_endpoint'}):
        logfire.configure(send_to_logfire=False, console=False)

    assert len(list(get_span_processors())) == 0
    assert len(list(get_metric_readers())) == 0

    [otel_log_processor] = get_log_record_processors()
    assert isinstance(otel_log_processor, BatchLogRecordProcessor)
    assert isinstance(otel_log_processor._exporter, OTLPLogExporter)  # type: ignore
    assert otel_log_processor._exporter._endpoint == 'otel_logs_endpoint'  # type: ignore


def test_metrics_false(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(LogfireConfig, '_initialize_credentials_from_token', lambda *args: None)  # type: ignore
    with patch.dict(os.environ, {'OTEL_EXPORTER_OTLP_METRICS_ENDPOINT': 'otel_metrics_endpoint'}):
        logfire.configure(send_to_logfire=True, token='foo', metrics=False)
        wait_for_check_token_thread()

    assert isinstance(get_meter_provider().provider, NoOpMeterProvider)  # type: ignore


def get_span_processors() -> Iterable[SpanProcessor]:
    [root] = get_tracer_provider().provider._active_span_processor._span_processors  # type: ignore
    assert isinstance(root, CheckSuppressInstrumentationProcessorWrapper)
    assert isinstance(root.processor, MainSpanProcessorWrapper)
    assert isinstance(root.processor.processor, SynchronousMultiSpanProcessor)

    return root.processor.processor._span_processors  # type: ignore


def get_metric_readers() -> Iterable[SpanProcessor]:
    return get_meter_provider().provider._sdk_config.metric_readers  # type: ignore


def get_log_record_processors() -> Iterable[LogRecordProcessor]:
    [processor] = get_logger_provider().provider._multi_log_record_processor._log_record_processors  # type: ignore
    assert isinstance(processor, CheckSuppressInstrumentationLogProcessorWrapper)
    processor = processor.processor
    assert isinstance(processor, MainLogProcessorWrapper)
    processor = processor.processor
    assert isinstance(processor, SynchronousMultiLogRecordProcessor)

    return processor._log_record_processors  # type: ignore


def test_dynamic_module_ignored_in_ensure_flush_after_aws_lambda(
    config_kwargs: dict[str, Any], capsys: pytest.CaptureFixture[str]
):
    from tests.import_used_for_tests.module_with_getattr import module_with_getattr_value

    assert module_with_getattr_value == 'module_with_getattr_value'

    logfire.configure(**config_kwargs)

    assert capsys.readouterr().err == ''


def test_collect_system_metrics_false():
    with inline_snapshot.extra.raises(
        snapshot(
            'ValueError: The `collect_system_metrics` argument has been removed. '
            'System metrics are no longer collected by default.'
        )
    ):
        logfire.configure(collect_system_metrics=False)  # type: ignore


def test_collect_system_metrics_true():
    with inline_snapshot.extra.raises(
        snapshot(
            'ValueError: The `collect_system_metrics` argument has been removed. '
            'Use `logfire.instrument_system_metrics()` instead.'
        )
    ):
        logfire.configure(collect_system_metrics=True)  # type: ignore


def test_unknown_kwargs():
    with inline_snapshot.extra.raises(snapshot('TypeError: configure() got unexpected keyword arguments: foo, bar')):
        logfire.configure(foo=1, bar=2)  # type: ignore


def test_project_name_deprecated():
    with inline_snapshot.extra.raises(
        snapshot('UserWarning: The `project_name` argument is deprecated and not needed.')
    ):
        logfire.configure(project_name='foo')  # type: ignore


def test_base_url_deprecated():
    with pytest.warns(UserWarning) as warnings:
        logfire.configure(base_url='foo')  # type: ignore
    assert len(warnings) == 1
    assert str(warnings[0].message) == snapshot(
        'The `base_url` argument is deprecated. Use `advanced=logfire.AdvancedOptions(base_url=...)` instead.'
    )
    assert GLOBAL_CONFIG.advanced.base_url == 'foo'


def test_combine_deprecated_and_new_advanced():
    with inline_snapshot.extra.raises(
        snapshot('ValueError: Cannot specify `base_url` and `advanced`. Use only `advanced`.')
    ):
        logfire.configure(base_url='foo', advanced=logfire.AdvancedOptions(base_url='bar'))  # type: ignore


def test_additional_metric_readers_deprecated():
    readers = [InMemoryMetricReader()]
    with pytest.warns(UserWarning) as warnings:
        logfire.configure(additional_metric_readers=readers)  # type: ignore
    assert len(warnings) == 1
    assert str(warnings[0].message) == snapshot(
        'The `additional_metric_readers` argument is deprecated. '
        'Use `metrics=logfire.MetricsOptions(additional_readers=[...])` instead.'
    )
    assert GLOBAL_CONFIG.metrics.additional_readers is readers  # type: ignore


def test_additional_metric_readers_combined_with_metrics():
    readers = [InMemoryMetricReader()]
    with inline_snapshot.extra.raises(
        snapshot(
            'ValueError: Cannot specify both `additional_metric_readers` and `metrics`. '
            'Use `metrics=logfire.MetricsOptions(additional_readers=[...])` instead.'
        )
    ):
        logfire.configure(additional_metric_readers=readers, metrics=False)  # type: ignore


def test_environment(config_kwargs: dict[str, Any], exporter: TestExporter):
    configure(**config_kwargs, service_version='1.2.3', environment='production')

    logfire.info('test1')

    assert exporter.exported_spans_as_dict(include_resources=True) == snapshot(
        [
            {
                'name': 'test1',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 1000000000,
                'attributes': {
                    'logfire.span_type': 'log',
                    'logfire.level_num': 9,
                    'logfire.msg_template': 'test1',
                    'logfire.msg': 'test1',
                    'code.filepath': 'test_configure.py',
                    'code.function': 'test_environment',
                    'code.lineno': 123,
                },
                'resource': {
                    'attributes': {
                        'service.instance.id': '00000000000000000000000000000000',
                        'telemetry.sdk.language': 'python',
                        'telemetry.sdk.name': 'opentelemetry',
                        'telemetry.sdk.version': '0.0.0',
                        'service.name': 'unknown_service',
                        'process.pid': 1234,
                        'process.runtime.name': 'cpython',
                        'process.runtime.version': IsStr(regex=PROCESS_RUNTIME_VERSION_REGEX),
                        'process.runtime.description': sys.version,
                        'service.version': '1.2.3',
                        'deployment.environment.name': 'production',
                    }
                },
            }
        ]
    )


def test_code_source(config_kwargs: dict[str, Any], exporter: TestExporter):
    configure(
        **config_kwargs,
        service_version='1.2.3',
        code_source=CodeSource(
            repository='https://github.com/pydantic/logfire',
            revision='main',
            root_path='logfire',
        ),
    )

    logfire.info('test1')

    assert exporter.exported_spans_as_dict(include_resources=True) == snapshot(
        [
            {
                'name': 'test1',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 1000000000,
                'attributes': {
                    'logfire.span_type': 'log',
                    'logfire.level_num': 9,
                    'logfire.msg_template': 'test1',
                    'logfire.msg': 'test1',
                    'code.filepath': 'test_configure.py',
                    'code.function': 'test_code_source',
                    'code.lineno': 123,
                },
                'resource': {
                    'attributes': {
                        'service.instance.id': '00000000000000000000000000000000',
                        'telemetry.sdk.language': 'python',
                        'telemetry.sdk.name': 'opentelemetry',
                        'telemetry.sdk.version': '0.0.0',
                        'service.name': 'unknown_service',
                        'process.pid': 1234,
                        'process.runtime.name': 'cpython',
                        'process.runtime.version': IsStr(regex=PROCESS_RUNTIME_VERSION_REGEX),
                        'process.runtime.description': sys.version,
                        'logfire.code.root_path': 'logfire',
                        'logfire.code.work_dir': os.getcwd(),
                        'vcs.repository.url.full': 'https://github.com/pydantic/logfire',
                        'vcs.repository.ref.revision': 'main',
                        'service.version': '1.2.3',
                    }
                },
            }
        ]
    )


def test_code_source_without_root_path(config_kwargs: dict[str, Any], exporter: TestExporter):
    configure(
        **config_kwargs,
        service_version='1.2.3',
        code_source=CodeSource(
            repository='https://github.com/pydantic/logfire',
            revision='main',
        ),
    )

    logfire.info('test1')

    assert exporter.exported_spans_as_dict(include_resources=True) == snapshot(
        [
            {
                'name': 'test1',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 1000000000,
                'attributes': {
                    'logfire.span_type': 'log',
                    'logfire.level_num': 9,
                    'logfire.msg_template': 'test1',
                    'logfire.msg': 'test1',
                    'code.filepath': 'test_configure.py',
                    'code.function': 'test_code_source_without_root_path',
                    'code.lineno': 123,
                },
                'resource': {
                    'attributes': {
                        'service.instance.id': '00000000000000000000000000000000',
                        'telemetry.sdk.language': 'python',
                        'telemetry.sdk.name': 'opentelemetry',
                        'telemetry.sdk.version': '0.0.0',
                        'service.name': 'unknown_service',
                        'process.pid': 1234,
                        'process.runtime.name': 'cpython',
                        'process.runtime.version': IsStr(regex=PROCESS_RUNTIME_VERSION_REGEX),
                        'process.runtime.description': sys.version,
                        'logfire.code.work_dir': os.getcwd(),
                        'vcs.repository.url.full': 'https://github.com/pydantic/logfire',
                        'vcs.repository.ref.revision': 'main',
                        'service.version': '1.2.3',
                    }
                },
            }
        ]
    )


def test_local_config(exporter: TestExporter, config_kwargs: dict[str, Any]):
    local_exporter = TestExporter()
    config_kwargs['additional_span_processors'] = [SimpleSpanProcessor(local_exporter)]
    local_logfire = logfire.configure(**config_kwargs, local=True)

    assert local_logfire != logfire.DEFAULT_LOGFIRE_INSTANCE
    assert local_logfire.config != logfire.DEFAULT_LOGFIRE_INSTANCE.config

    logfire.info('test1')
    local_logfire.info('test2')

    assert exporter.exported_spans_as_dict() == snapshot(
        [
            {
                'name': 'test1',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 1000000000,
                'attributes': {
                    'logfire.span_type': 'log',
                    'logfire.level_num': 9,
                    'logfire.msg_template': 'test1',
                    'logfire.msg': 'test1',
                    'code.filepath': 'test_configure.py',
                    'code.function': 'test_local_config',
                    'code.lineno': 123,
                },
            }
        ]
    )
    assert local_exporter.exported_spans_as_dict() == snapshot(
        [
            {
                'name': 'test2',
                'context': {
                    'trace_id': 2,
                    'span_id': 2,
                    'is_remote': False,
                },
                'parent': None,
                'start_time': 2000000000,
                'end_time': 2000000000,
                'attributes': {
                    'logfire.span_type': 'log',
                    'logfire.level_num': 9,
                    'logfire.msg_template': 'test2',
                    'logfire.msg': 'test2',
                    'code.filepath': 'test_configure.py',
                    'code.function': 'test_local_config',
                    'code.lineno': 123,
                },
            }
        ]
    )


def test_distributed_tracing_default(exporter: TestExporter, config_kwargs: dict[str, Any]):
    config_kwargs['distributed_tracing'] = None
    logfire.configure(**config_kwargs)

    assert isinstance(get_global_textmap(), WarnOnExtractTraceContextPropagator)
    assert get_global_textmap().fields == {'baggage', 'traceparent', 'tracestate'}

    with logfire.span('span1'):
        ctx = propagate.get_context()

    with propagate.attach_context(ctx):
        logfire.info('test1')

    with inline_snapshot.extra.warns(
        snapshot(
            [
                'RuntimeWarning: Found propagated trace context. See https://logfire.pydantic.dev/docs/how-to-guides/distributed-tracing/#unintentional-distributed-tracing.'
            ]
        )
    ):
        with propagate.attach_context(ctx, third_party=True):
            logfire.info('test2')

    # Only warn once.
    with propagate.attach_context(ctx, third_party=True):
        logfire.info('test3')

    assert exporter.exported_spans_as_dict() == snapshot(
        [
            {
                'name': 'span1',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 2000000000,
                'attributes': {
                    'code.filepath': 'test_configure.py',
                    'code.function': 'test_distributed_tracing_default',
                    'code.lineno': 123,
                    'logfire.msg_template': 'span1',
                    'logfire.msg': 'span1',
                    'logfire.span_type': 'span',
                },
            },
            {
                'name': 'test1',
                'context': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': True},
                'start_time': 3000000000,
                'end_time': 3000000000,
                'attributes': {
                    'logfire.span_type': 'log',
                    'logfire.level_num': 9,
                    'logfire.msg_template': 'test1',
                    'logfire.msg': 'test1',
                    'code.filepath': 'test_configure.py',
                    'code.function': 'test_distributed_tracing_default',
                    'code.lineno': 123,
                },
            },
            {
                'name': 'Found propagated trace context. See https://logfire.pydantic.dev/docs/how-to-guides/distributed-tracing/#unintentional-distributed-tracing.',
                'context': {'trace_id': 2, 'span_id': 4, 'is_remote': False},
                'parent': None,
                'start_time': 4000000000,
                'end_time': 4000000000,
                'attributes': {
                    'logfire.span_type': 'log',
                    'logfire.level_num': 13,
                    'logfire.msg_template': 'Found propagated trace context. See https://logfire.pydantic.dev/docs/how-to-guides/distributed-tracing/#unintentional-distributed-tracing.',
                    'logfire.msg': 'Found propagated trace context. See https://logfire.pydantic.dev/docs/how-to-guides/distributed-tracing/#unintentional-distributed-tracing.',
                    'code.filepath': 'test_configure.py',
                    'code.function': 'test_distributed_tracing_default',
                    'code.lineno': 123,
                },
            },
            {
                'name': 'test2',
                'context': {'trace_id': 1, 'span_id': 5, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': True},
                'start_time': 5000000000,
                'end_time': 5000000000,
                'attributes': {
                    'logfire.span_type': 'log',
                    'logfire.level_num': 9,
                    'logfire.msg_template': 'test2',
                    'logfire.msg': 'test2',
                    'code.filepath': 'test_configure.py',
                    'code.function': 'test_distributed_tracing_default',
                    'code.lineno': 123,
                },
            },
            {
                'name': 'test3',
                'context': {'trace_id': 1, 'span_id': 6, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': True},
                'start_time': 6000000000,
                'end_time': 6000000000,
                'attributes': {
                    'logfire.span_type': 'log',
                    'logfire.level_num': 9,
                    'logfire.msg_template': 'test3',
                    'logfire.msg': 'test3',
                    'code.filepath': 'test_configure.py',
                    'code.function': 'test_distributed_tracing_default',
                    'code.lineno': 123,
                },
            },
        ]
    )


def test_distributed_tracing_enabled(exporter: TestExporter):
    assert isinstance(get_global_textmap(), CompositePropagator)
    assert get_global_textmap().fields == {'baggage', 'traceparent', 'tracestate'}

    with logfire.span('span1'):
        ctx = propagate.get_context()

    with propagate.attach_context(ctx):
        logfire.info('test1')

    with propagate.attach_context(ctx, third_party=True):
        logfire.info('test2')

    assert exporter.exported_spans_as_dict() == snapshot(
        [
            {
                'name': 'span1',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 2000000000,
                'attributes': {
                    'code.filepath': 'test_configure.py',
                    'code.function': 'test_distributed_tracing_enabled',
                    'code.lineno': 123,
                    'logfire.msg_template': 'span1',
                    'logfire.msg': 'span1',
                    'logfire.span_type': 'span',
                },
            },
            {
                'name': 'test1',
                'context': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': True},
                'start_time': 3000000000,
                'end_time': 3000000000,
                'attributes': {
                    'logfire.span_type': 'log',
                    'logfire.level_num': 9,
                    'logfire.msg_template': 'test1',
                    'logfire.msg': 'test1',
                    'code.filepath': 'test_configure.py',
                    'code.function': 'test_distributed_tracing_enabled',
                    'code.lineno': 123,
                },
            },
            {
                'name': 'test2',
                'context': {'trace_id': 1, 'span_id': 4, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': True},
                'start_time': 4000000000,
                'end_time': 4000000000,
                'attributes': {
                    'logfire.span_type': 'log',
                    'logfire.level_num': 9,
                    'logfire.msg_template': 'test2',
                    'logfire.msg': 'test2',
                    'code.filepath': 'test_configure.py',
                    'code.function': 'test_distributed_tracing_enabled',
                    'code.lineno': 123,
                },
            },
        ]
    )


def test_distributed_tracing_disabled(exporter: TestExporter, config_kwargs: dict[str, Any]):
    config_kwargs['distributed_tracing'] = False
    logfire.configure(**config_kwargs)

    assert isinstance(get_global_textmap(), NoExtractTraceContextPropagator)
    assert get_global_textmap().fields == {'baggage', 'traceparent', 'tracestate'}

    with logfire.span('span1'):
        ctx = propagate.get_context()

    with propagate.attach_context(ctx):
        logfire.info('test1')

    with propagate.attach_context(ctx, third_party=True):
        logfire.info('test2')

    assert exporter.exported_spans_as_dict() == snapshot(
        [
            {
                'name': 'span1',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 2000000000,
                'attributes': {
                    'code.filepath': 'test_configure.py',
                    'code.function': 'test_distributed_tracing_disabled',
                    'code.lineno': 123,
                    'logfire.msg_template': 'span1',
                    'logfire.msg': 'span1',
                    'logfire.span_type': 'span',
                },
            },
            {
                'name': 'test1',
                'context': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': True},
                'start_time': 3000000000,
                'end_time': 3000000000,
                'attributes': {
                    'logfire.span_type': 'log',
                    'logfire.level_num': 9,
                    'logfire.msg_template': 'test1',
                    'logfire.msg': 'test1',
                    'code.filepath': 'test_configure.py',
                    'code.function': 'test_distributed_tracing_disabled',
                    'code.lineno': 123,
                },
            },
            {
                'name': 'test2',
                'context': {'trace_id': 2, 'span_id': 4, 'is_remote': False},
                'parent': None,
                'start_time': 4000000000,
                'end_time': 4000000000,
                'attributes': {
                    'logfire.span_type': 'log',
                    'logfire.level_num': 9,
                    'logfire.msg_template': 'test2',
                    'logfire.msg': 'test2',
                    'code.filepath': 'test_configure.py',
                    'code.function': 'test_distributed_tracing_disabled',
                    'code.lineno': 123,
                },
            },
        ]
    )


def test_quiet_span_exporter(caplog: LogCaptureFixture):
    class ConnectionErrorExporter(SpanExporter):
        def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
            raise requests.exceptions.ConnectionError()

    exporter = QuietSpanExporter(ConnectionErrorExporter())

    assert exporter.export([]) == SpanExportResult.FAILURE
    assert not caplog.messages


def test_staging_token_regions():
    assert get_base_url_from_token('pylf_v1_stagingeu_123456') == 'https://logfire-eu.pydantic.info'
    assert get_base_url_from_token('pylf_v1_stagingus_123456') == 'https://logfire-us.pydantic.info'
