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
import requests_mock
from inline_snapshot import snapshot
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.metrics import get_meter_provider
from opentelemetry.sdk.metrics._internal.export import PeriodicExportingMetricReader
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.trace import ReadableSpan, SpanProcessor
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    ConsoleSpanExporter,
    SimpleSpanProcessor,
    SpanExporter,
    SpanExportResult,
)
from opentelemetry.trace import get_tracer_provider
from pytest import LogCaptureFixture

import logfire
from logfire import configure
from logfire._internal.config import (
    GLOBAL_CONFIG,
    ConsoleOptions,
    LogfireConfig,
    LogfireCredentials,
    sanitize_project_name,
)
from logfire._internal.exporters.console import ShowParentsConsoleSpanExporter
from logfire._internal.exporters.fallback import FallbackSpanExporter
from logfire._internal.exporters.file import WritingFallbackWarning
from logfire._internal.exporters.processor_wrapper import MainSpanProcessorWrapper
from logfire._internal.exporters.quiet_metrics import QuietMetricExporter
from logfire._internal.exporters.remove_pending import RemovePendingSpansExporter
from logfire._internal.exporters.wrapper import WrapperSpanExporter
from logfire._internal.integrations.executors import deserialize_config, serialize_config
from logfire._internal.tracer import PendingSpanProcessor
from logfire.exceptions import LogfireConfigError
from logfire.testing import IncrementalIdGenerator, TestExporter, TimeGenerator


def test_propagate_config_to_tags() -> None:
    time_generator = TimeGenerator()
    exporter = TestExporter()

    tags1 = logfire.with_tags('tag1', 'tag2')

    configure(
        send_to_logfire=False,
        console=False,
        ns_timestamp_generator=time_generator,
        id_generator=IncrementalIdGenerator(),
        additional_span_processors=[SimpleSpanProcessor(exporter)],
        additional_metric_readers=[InMemoryMetricReader()],
    )

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
                'name': 'root (pending)',
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
                'name': 'child (pending)',
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
                'name': 'root (pending)',
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
                'name': 'child (pending)',
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
                'name': 'root (pending)',
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
                'name': 'child (pending)',
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


def test_read_config_from_environment_variables() -> None:
    assert LogfireConfig().pydantic_plugin.record == 'off'

    with patch.dict(os.environ, {'LOGFIRE_PYDANTIC_PLUGIN_RECORD': 'all'}):
        assert LogfireConfig().pydantic_plugin.record == 'all'
    with patch.dict(os.environ, {'LOGFIRE_PYDANTIC_PLUGIN_RECORD': 'test'}):
        with pytest.raises(
            LogfireConfigError,
            match="Expected pydantic_plugin_record to be one of \\('off', 'all', 'failure', 'metrics'\\), got 'test'",
        ):
            LogfireConfig()

    assert LogfireConfig().pydantic_plugin.include == set()
    with patch.dict(os.environ, {'LOGFIRE_PYDANTIC_PLUGIN_INCLUDE': 'test'}):
        assert LogfireConfig().pydantic_plugin.include == {'test'}
    with patch.dict(os.environ, {'LOGFIRE_PYDANTIC_PLUGIN_INCLUDE': 'test1, test2'}):
        assert LogfireConfig().pydantic_plugin.include == {'test1', 'test2'}

    assert LogfireConfig().pydantic_plugin.exclude == set()
    with patch.dict(os.environ, {'LOGFIRE_PYDANTIC_PLUGIN_EXCLUDE': 'test'}):
        assert LogfireConfig().pydantic_plugin.exclude == {'test'}
    with patch.dict(os.environ, {'LOGFIRE_PYDANTIC_PLUGIN_EXCLUDE': 'test1, test2'}):
        assert LogfireConfig().pydantic_plugin.exclude == {'test1', 'test2'}


def test_read_config_from_pyproject_toml(tmp_path: Path) -> None:
    (tmp_path / 'pyproject.toml').write_text(
        f"""
        [tool.logfire]
        base_url = "https://api.logfire.io"
        send_to_logfire = false
        project_name = "test"
        console_colors = "never"
        console_include_timestamp = false
        data_dir = "{tmp_path}"
        pydantic_plugin_record = "metrics"
        pydantic_plugin_include = " test1, test2"
        pydantic_plugin_exclude = "test3 ,test4"
        """
    )

    configure(
        config_dir=tmp_path,
        additional_metric_readers=[InMemoryMetricReader()],
    )

    assert GLOBAL_CONFIG.base_url == 'https://api.logfire.io'
    assert GLOBAL_CONFIG.send_to_logfire is False
    assert GLOBAL_CONFIG.project_name == 'test'
    assert GLOBAL_CONFIG.console
    assert GLOBAL_CONFIG.console.colors == 'never'
    assert GLOBAL_CONFIG.console.include_timestamps is False
    assert GLOBAL_CONFIG.data_dir == tmp_path
    assert GLOBAL_CONFIG.pydantic_plugin.record == 'metrics'
    assert GLOBAL_CONFIG.pydantic_plugin.include == {'test1', 'test2'}
    assert GLOBAL_CONFIG.pydantic_plugin.exclude == {'test3', 'test4'}


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


def test_configure_fallback_path(tmp_path: str) -> None:
    request_mocker = requests_mock.Mocker()
    request_mocker.get(
        'https://logfire-api.pydantic.dev/v1/info',
        json={'project_name': 'myproject', 'project_url': 'fake_project_url'},
    )

    class FailureExporter(SpanExporter):
        def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
            # This should cause FallbackSpanExporter to call its own fallback file exporter.
            return SpanExportResult.FAILURE

    data_dir = Path(tmp_path) / 'logfire_data'
    with request_mocker:
        logfire.configure(
            send_to_logfire=True,
            data_dir=data_dir,
            token='abc1',
            console=False,
        )
        wait_for_check_token_thread()

    send_to_logfire_processor, *_ = get_span_processors()
    # It's OK if these processor/exporter types change.
    # We just need access to the FallbackSpanExporter either way to swap out its underlying exporter.
    assert isinstance(send_to_logfire_processor, MainSpanProcessorWrapper)
    batch_span_processor = send_to_logfire_processor.processor
    assert isinstance(batch_span_processor, BatchSpanProcessor)
    exporter = batch_span_processor.span_exporter
    assert isinstance(exporter, WrapperSpanExporter)
    fallback_exporter = exporter.wrapped_exporter
    assert isinstance(fallback_exporter, FallbackSpanExporter)
    fallback_exporter.exporter = FailureExporter()

    with logfire.span('test'):
        pass

    assert not data_dir.exists()
    path = data_dir / 'logfire_spans.bin'

    with pytest.warns(WritingFallbackWarning, match=f'Failed to export spans, writing to fallback file: {path}'):
        logfire.force_flush()

    assert path.exists()


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
            'https://logfire-api.pydantic.dev/v1/info',
            json={'project_name': 'myproject', 'project_url': 'fake_project_url'},
        )

        with request_mocker:
            logfire.configure(
                send_to_logfire=True,
                token='abc1',
                console=False,
                fast_shutdown=True,
            )
            wait_for_check_token_thread()

        send_to_logfire_processor, *_ = get_span_processors()
        assert isinstance(send_to_logfire_processor, MainSpanProcessorWrapper)
        batch_span_processor = send_to_logfire_processor.processor
        assert isinstance(batch_span_processor, BatchSpanProcessor)

        batch_span_processor.span_exporter = TrackingExporter()
        return batch_span_processor.span_exporter

    def check_delays(exp: TrackingExporter, min_delay: float, max_delay: float) -> None:
        for delay in exp.export_delays:
            assert min_delay < delay < max_delay, f'delay was {delay}, which is not between {min_delay} and {max_delay}'

    # test the default value
    exporter = configure_tracking_exporter()
    while not exporter.export_delays:
        with logfire.span('test'):
            pass
        sleep(0.1)
    check_delays(exporter, 0.4, 1.0)  # our default is 500ms

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
        configure(
            token='abc2',
            service_version='1.2.3',
            additional_metric_readers=[InMemoryMetricReader()],
        )

        assert GLOBAL_CONFIG.service_version == '1.2.3'

        configure(
            token='abc3',
            additional_metric_readers=[InMemoryMetricReader()],
        )

        assert GLOBAL_CONFIG.service_version == git_sha

        dir = os.getcwd()

        try:
            os.chdir(tmp_path)
            configure(
                token='abc4',
                additional_metric_readers=[InMemoryMetricReader()],
            )
            assert GLOBAL_CONFIG.service_version is None
        finally:
            os.chdir(dir)

        wait_for_check_token_thread()


def test_otel_service_name_env_var() -> None:
    time_generator = TimeGenerator()
    exporter = TestExporter()

    with patch.dict(os.environ, {'OTEL_SERVICE_NAME': 'potato'}):
        configure(
            service_version='1.2.3',
            send_to_logfire=False,
            console=False,
            ns_timestamp_generator=time_generator,
            id_generator=IncrementalIdGenerator(),
            additional_span_processors=[SimpleSpanProcessor(exporter)],
            additional_metric_readers=[InMemoryMetricReader()],
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
                        'process.pid': 1234,
                    }
                },
            }
        ]
    )


def test_otel_otel_resource_attributes_env_var() -> None:
    time_generator = TimeGenerator()
    exporter = TestExporter()

    with patch.dict(
        os.environ,
        {'OTEL_RESOURCE_ATTRIBUTES': 'service.name=banana,service.version=1.2.3,service.instance.id=instance_id'},
    ):
        configure(
            send_to_logfire=False,
            console=False,
            ns_timestamp_generator=time_generator,
            id_generator=IncrementalIdGenerator(),
            additional_span_processors=[SimpleSpanProcessor(exporter)],
            additional_metric_readers=[InMemoryMetricReader()],
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
                    }
                },
            }
        ]
    )


def test_otel_service_name_has_priority_on_otel_resource_attributes_service_name_env_var() -> None:
    time_generator = TimeGenerator()
    exporter = TestExporter()

    with patch.dict(
        os.environ,
        dict(OTEL_SERVICE_NAME='potato', OTEL_RESOURCE_ATTRIBUTES='service.name=banana,service.version=1.2.3'),
    ):
        configure(
            send_to_logfire=False,
            console=False,
            ns_timestamp_generator=time_generator,
            id_generator=IncrementalIdGenerator(),
            additional_span_processors=[SimpleSpanProcessor(exporter)],
            additional_metric_readers=[InMemoryMetricReader()],
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
        pydantic_plugin=logfire.PydanticPlugin(record='all'),
        console=logfire.ConsoleOptions(verbose=True),
        tail_sampling=logfire.TailSamplingOptions(),
        scrubbing=logfire.ScrubbingOptions(),
    )

    for field in dataclasses.fields(GLOBAL_CONFIG):
        # Check that the full set of dataclass fields is known.
        # If a new field appears here, make sure it gets deserialized properly in configure, and tested here.
        assert dataclasses.is_dataclass(getattr(GLOBAL_CONFIG, field.name)) == (
            field.name in ['pydantic_plugin', 'console', 'tail_sampling', 'scrubbing']
        )

    serialized = serialize_config()
    deserialize_config(serialized)
    serialized2 = serialize_config()

    def normalize(s: dict[str, Any]) -> dict[str, Any]:
        for value in s.values():
            assert not dataclasses.is_dataclass(value)
        # These values get deepcopied by dataclasses.asdict, so we can't compare them directly
        return {k: v for k, v in s.items() if k not in ['id_generator']}

    assert normalize(serialized) == normalize(serialized2)

    assert isinstance(GLOBAL_CONFIG.pydantic_plugin, logfire.PydanticPlugin)
    assert isinstance(GLOBAL_CONFIG.console, logfire.ConsoleOptions)
    assert isinstance(GLOBAL_CONFIG.tail_sampling, logfire.TailSamplingOptions)
    assert isinstance(GLOBAL_CONFIG.scrubbing, logfire.ScrubbingOptions)


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
        create_project_response = {
            'json': {
                'project_name': 'myproject',
                'token': 'fake_token',
                'project_url': 'fake_project_url',
            }
        }
        request_mocker.post('https://logfire-api.pydantic.dev/v1/projects/fake_org', [create_project_response])

        logfire.configure(send_to_logfire=True)

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

        logfire.configure(
            send_to_logfire=True,
        )

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

        assert confirm_mock.mock_calls == [
            call('Do you want to use one of your existing projects? ', default=True),
            call('The project will be created in the organization "fake_org". Continue?', default=True),
        ]


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

        for request in request_mocker.request_history:
            assert request.headers['Authorization'] == 'fake_user_token'

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


def test_send_to_logfire_false() -> None:
    """
    Test that with send_to_logfire=False, that logic is NOT triggered.
    """
    with mock.patch('logfire._internal.config.Confirm.ask', side_effect=RuntimeError):
        configure(send_to_logfire=False, console=False)


def test_send_to_logfire_if_token_present() -> None:
    with mock.patch('logfire._internal.config.Confirm.ask', side_effect=RuntimeError):
        configure(send_to_logfire='if-token-present', console=False)


def test_send_to_logfire_if_token_present_empty() -> None:
    os.environ['LOGFIRE_TOKEN'] = ''
    try:
        with ExitStack() as stack:
            stack.enter_context(mock.patch('logfire._internal.config.Confirm.ask', side_effect=RuntimeError))
            requests_mocker = stack.enter_context(requests_mock.Mocker())
            configure(send_to_logfire='if-token-present', console=False)
            assert len(requests_mocker.request_history) == 0
    finally:
        del os.environ['LOGFIRE_TOKEN']


def wait_for_check_token_thread():
    for thread in threading.enumerate():
        if thread.name == 'check_logfire_token':  # pragma: no cover
            thread.join()


def test_send_to_logfire_if_token_present_not_empty(capsys: pytest.CaptureFixture[str]) -> None:
    os.environ['LOGFIRE_TOKEN'] = 'foobar'
    try:
        with requests_mock.Mocker() as request_mocker:
            request_mocker.get(
                'https://logfire-api.pydantic.dev/v1/info',
                json={'project_name': 'myproject', 'project_url': 'fake_project_url'},
            )
            configure(send_to_logfire='if-token-present', console=False)
            wait_for_check_token_thread()
            assert len(request_mocker.request_history) == 1
            assert capsys.readouterr().err == 'Logfire project URL: fake_project_url\n'
    finally:
        del os.environ['LOGFIRE_TOKEN']


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


def test_get_user_token_not_authenticated(default_credentials: Path):
    with patch('logfire._internal.config.DEFAULT_FILE', default_credentials):
        with pytest.raises(
            LogfireConfigError, match='You are not authenticated. Please run `logfire auth` to authenticate.'
        ):
            # Use a port that we don't use for local development to reduce conflicts with local configuration
            LogfireCredentials._get_user_token(logfire_api_url='http://localhost:8234')  # type: ignore


def test_initialize_credentials_from_token_unreachable():
    with pytest.warns(
        UserWarning,
        match="Logfire API is unreachable, you may have trouble sending data. Error: Invalid URL '/v1/info': No scheme supplied.",
    ):
        LogfireConfig(base_url='')._initialize_credentials_from_token('some-token')  # type: ignore


def test_initialize_credentials_from_token_invalid_token():
    with ExitStack() as stack:
        request_mocker = requests_mock.Mocker()
        stack.enter_context(request_mocker)
        request_mocker.get('https://logfire-api.pydantic.dev/v1/info', text='Error', status_code=401)

        with pytest.warns(match='Invalid Logfire token.'):
            LogfireConfig()._initialize_credentials_from_token('some-token')  # type: ignore


def test_initialize_credentials_from_token_unhealthy():
    with ExitStack() as stack:
        request_mocker = requests_mock.Mocker()
        stack.enter_context(request_mocker)
        request_mocker.get('https://logfire-api.pydantic.dev/v1/info', text='Error', status_code=500)

        with pytest.warns(
            UserWarning, match='Logfire API is unhealthy, you may have trouble sending data. Status code: 500'
        ):
            LogfireConfig()._initialize_credentials_from_token('some-token')  # type: ignore


def test_configure_twice_no_warning(caplog: LogCaptureFixture):
    logfire.configure(send_to_logfire=False)
    assert not caplog.messages


def test_send_to_logfire_under_pytest():
    """
    Test that the `send_to_logfire` parameter is set to False when running under pytest.
    """
    assert 'PYTEST_CURRENT_TEST' in os.environ
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

    [console_processor, send_to_logfire_processor, pending_span_processor] = get_span_processors()

    assert isinstance(console_processor, MainSpanProcessorWrapper)
    assert isinstance(console_processor.processor, SimpleSpanProcessor)
    assert isinstance(console_processor.processor.span_exporter, ShowParentsConsoleSpanExporter)

    assert isinstance(send_to_logfire_processor, MainSpanProcessorWrapper)
    assert isinstance(send_to_logfire_processor.processor, BatchSpanProcessor)
    assert isinstance(send_to_logfire_processor.processor.span_exporter, RemovePendingSpansExporter)

    assert isinstance(pending_span_processor, PendingSpanProcessor)
    assert pending_span_processor.other_processors == (console_processor, send_to_logfire_processor)

    [logfire_metric_reader] = get_metric_readers()
    assert isinstance(logfire_metric_reader, PeriodicExportingMetricReader)
    assert isinstance(logfire_metric_reader._exporter, QuietMetricExporter)  # type: ignore


def test_custom_exporters():
    custom_span_processor = SimpleSpanProcessor(ConsoleSpanExporter())
    custom_metric_reader = InMemoryMetricReader()

    logfire.configure(
        send_to_logfire=False,
        console=False,
        additional_span_processors=[custom_span_processor],
        additional_metric_readers=[custom_metric_reader],
    )

    [custom_processor_wrapper] = get_span_processors()
    assert isinstance(custom_processor_wrapper, MainSpanProcessorWrapper)
    assert custom_processor_wrapper.processor is custom_span_processor

    [custom_metric_reader2] = get_metric_readers()
    assert custom_metric_reader2 is custom_metric_reader


def test_otel_exporter_otlp_endpoint_env_var():
    # Setting this env var creates an OTLPSpanExporter and an OTLPMetricExporter
    with patch.dict(os.environ, {'OTEL_EXPORTER_OTLP_ENDPOINT': 'otel_endpoint'}):
        logfire.configure(send_to_logfire=False, console=False)

    [otel_processor] = get_span_processors()
    assert isinstance(otel_processor, MainSpanProcessorWrapper)
    assert isinstance(otel_processor.processor, BatchSpanProcessor)
    assert isinstance(otel_processor.processor.span_exporter, OTLPSpanExporter)
    assert otel_processor.processor.span_exporter._endpoint == 'otel_endpoint/v1/traces'  # type: ignore

    [otel_metric_reader] = get_metric_readers()
    assert isinstance(otel_metric_reader, PeriodicExportingMetricReader)
    assert isinstance(otel_metric_reader._exporter, OTLPMetricExporter)  # type: ignore
    assert otel_metric_reader._exporter._endpoint == 'otel_endpoint/v1/metrics'  # type: ignore


def test_otel_traces_exporter_env_var():
    # Setting OTEL_TRACES_EXPORTER to something other than otlp prevents creating an OTLPSpanExporter
    with patch.dict(os.environ, {'OTEL_EXPORTER_OTLP_ENDPOINT': 'otel_endpoint2', 'OTEL_TRACES_EXPORTER': 'grpc'}):
        logfire.configure(send_to_logfire=False, console=False)

    assert len(list(get_span_processors())) == 0

    [otel_metric_reader] = get_metric_readers()
    assert isinstance(otel_metric_reader, PeriodicExportingMetricReader)
    assert isinstance(otel_metric_reader._exporter, OTLPMetricExporter)  # type: ignore
    assert otel_metric_reader._exporter._endpoint == 'otel_endpoint2/v1/metrics'  # type: ignore


def test_otel_metrics_exporter_env_var():
    # Setting OTEL_METRICS_EXPORTER to something other than otlp prevents creating an OTLPMetricExporter
    with patch.dict(os.environ, {'OTEL_EXPORTER_OTLP_ENDPOINT': 'otel_endpoint3', 'OTEL_METRICS_EXPORTER': 'none'}):
        logfire.configure(send_to_logfire=False, console=False)

    [otel_processor] = get_span_processors()
    assert isinstance(otel_processor, MainSpanProcessorWrapper)
    assert isinstance(otel_processor.processor, BatchSpanProcessor)
    assert isinstance(otel_processor.processor.span_exporter, OTLPSpanExporter)
    assert otel_processor.processor.span_exporter._endpoint == 'otel_endpoint3/v1/traces'  # type: ignore

    assert len(list(get_metric_readers())) == 0


def test_otel_exporter_otlp_traces_endpoint_env_var():
    # Setting just OTEL_EXPORTER_OTLP_TRACES_ENDPOINT only creates an OTLPSpanExporter
    with patch.dict(os.environ, {'OTEL_EXPORTER_OTLP_TRACES_ENDPOINT': 'otel_traces_endpoint'}):
        logfire.configure(send_to_logfire=False, console=False)

    [otel_processor] = get_span_processors()
    assert isinstance(otel_processor, MainSpanProcessorWrapper)
    assert isinstance(otel_processor.processor, BatchSpanProcessor)
    assert isinstance(otel_processor.processor.span_exporter, OTLPSpanExporter)
    assert otel_processor.processor.span_exporter._endpoint == 'otel_traces_endpoint'  # type: ignore

    assert len(list(get_metric_readers())) == 0


def test_otel_exporter_otlp_metrics_endpoint_env_var():
    # Setting just OTEL_EXPORTER_OTLP_METRICS_ENDPOINT only creates an OTLPMetricExporter
    with patch.dict(os.environ, {'OTEL_EXPORTER_OTLP_METRICS_ENDPOINT': 'otel_metrics_endpoint'}):
        logfire.configure(send_to_logfire=False, console=False)

    assert len(list(get_span_processors())) == 0

    [otel_metric_reader] = get_metric_readers()
    assert isinstance(otel_metric_reader, PeriodicExportingMetricReader)
    assert isinstance(otel_metric_reader._exporter, OTLPMetricExporter)  # type: ignore
    assert otel_metric_reader._exporter._endpoint == 'otel_metrics_endpoint'  # type: ignore


def get_span_processors() -> Iterable[SpanProcessor]:
    return get_tracer_provider().provider._active_span_processor._span_processors  # type: ignore


def get_metric_readers() -> Iterable[SpanProcessor]:
    return get_meter_provider().provider._sdk_config.metric_readers  # type: ignore


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
