from __future__ import annotations

import dataclasses
import json
import os
from contextlib import ExitStack
from pathlib import Path
from typing import Iterable, Mapping, Sequence
from unittest import mock
from unittest.mock import call, patch

import pytest
import requests
import requests_mock
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export import SimpleSpanProcessor, SpanExporter, SpanExportResult
from requests.adapters import HTTPAdapter

import logfire
from logfire import configure
from logfire._config import (
    GLOBAL_CONFIG,
    ConsoleOptions,
    LogfireConfig,
    LogfireConfigError,
    sanitize_project_name,
)
from logfire.exporters._fallback import FallbackSpanExporter
from logfire.exporters._file import WritingFallbackWarning
from logfire.exporters._wrapper import WrapperSpanExporter
from logfire.integrations._executors import deserialize_config, serialize_config
from logfire.testing import IncrementalIdGenerator, TestExporter, TimeGenerator


class StubAdapter(HTTPAdapter):
    """
    A Transport Adapter that stores all requests sent, and provides pre-canned responses.
    """

    def __init__(self, requests: list[requests.PreparedRequest], responses: Iterable[requests.Response]) -> None:
        self.requests = requests
        self.responses = iter(responses)
        super().__init__()

    def send(
        self,
        request: requests.PreparedRequest,
        stream: bool = False,
        timeout: None | float | tuple[float, float] | tuple[float, None] = None,
        verify: bool | str = True,
        cert: None | bytes | str | tuple[bytes | str, bytes | str] = None,
        proxies: Mapping[str, str] | None = None,
    ) -> requests.Response:
        self.requests.append(request)
        return next(self.responses)


def test_propagate_config_to_tags() -> None:
    time_generator = TimeGenerator()
    exporter = TestExporter()

    tags1 = logfire.with_tags('tag1', 'tag2')

    configure(
        send_to_logfire=False,
        console=False,
        ns_timestamp_generator=time_generator,
        id_generator=IncrementalIdGenerator(),
        processors=[SimpleSpanProcessor(exporter)],
        metric_readers=[InMemoryMetricReader()],
    )

    tags2 = logfire.with_tags('tag3', 'tag4')

    for lf in (logfire, tags1, tags2):
        with lf.span('root'):
            with lf.span('child'):
                logfire.info('test1')
                tags1.info('test2')
                tags2.info('test3')

    # insert_assert(exporter.exported_spans_as_dict(_include_pending_spans=True))
    assert exporter.exported_spans_as_dict(_include_pending_spans=True) == [
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
                'logfire.level_name': 'info',
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
                'logfire.level_name': 'info',
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
                'logfire.level_name': 'info',
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
                'logfire.level_name': 'info',
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
                'logfire.level_name': 'info',
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
                'logfire.level_name': 'info',
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
                'logfire.level_name': 'info',
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
                'logfire.level_name': 'info',
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
                'logfire.level_name': 'info',
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
        collect_system_metrics = false
        pydantic_plugin_record = "metrics"
        pydantic_plugin_include = " test1, test2"
        pydantic_plugin_exclude = "test3 ,test4"
        """
    )

    configure(
        config_dir=tmp_path,
        metric_readers=[InMemoryMetricReader()],
    )

    assert GLOBAL_CONFIG.base_url == 'https://api.logfire.io'
    assert GLOBAL_CONFIG.send_to_logfire is False
    assert GLOBAL_CONFIG.project_name == 'test'
    assert GLOBAL_CONFIG.console.colors == 'never'
    assert GLOBAL_CONFIG.console.include_timestamps is False
    assert GLOBAL_CONFIG.data_dir == tmp_path
    assert GLOBAL_CONFIG.collect_system_metrics is False
    assert GLOBAL_CONFIG.pydantic_plugin.record == 'metrics'
    assert GLOBAL_CONFIG.pydantic_plugin.include == {'test1', 'test2'}
    assert GLOBAL_CONFIG.pydantic_plugin.exclude == {'test3', 'test4'}


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
    logfire_api_session = requests.Session()
    response = requests.Response()
    response.status_code = 200
    check_logfire_backend_adapter = StubAdapter(requests=[], responses=[response])
    logfire_api_session.adapters['https://'] = check_logfire_backend_adapter

    class FailureExporter(SpanExporter):
        def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
            # This should cause FallbackSpanExporter to call its own fallback file exporter.
            return SpanExportResult.FAILURE

    def default_span_processor(exporter: SpanExporter) -> SimpleSpanProcessor:
        # It's OK if these exporter types change.
        # We just need access to the FallbackSpanExporter either way to swap out its underlying exporter.
        assert isinstance(exporter, WrapperSpanExporter)
        fallback_exporter = exporter.wrapped_exporter
        assert isinstance(fallback_exporter, FallbackSpanExporter)
        fallback_exporter.exporter = FailureExporter()

        return SimpleSpanProcessor(exporter)

    data_dir = Path(tmp_path) / 'logfire_data'
    logfire.configure(
        data_dir=data_dir,
        token='abc',
        default_span_processor=default_span_processor,
        logfire_api_session=logfire_api_session,
        metric_readers=[InMemoryMetricReader()],
    )

    assert not data_dir.exists()
    path = data_dir / 'logfire_spans.bin'

    with pytest.warns(WritingFallbackWarning, match=f'Failed to export spans, writing to fallback file: {path}'):
        with logfire.span('test'):
            pass

    assert path.exists()


def test_configure_service_version(tmp_path: str) -> None:
    logfire_api_session = requests.Session()
    response = requests.Response()
    response.status_code = 200
    check_logfire_backend_adapter = StubAdapter(requests=[], responses=[response] * 3)
    logfire_api_session.adapters['https://'] = check_logfire_backend_adapter

    import subprocess

    git_sha = subprocess.check_output(['git', 'rev-parse', 'HEAD']).decode('ascii').strip()

    configure(
        token='abc',
        service_version='1.2.3',
        logfire_api_session=logfire_api_session,
        metric_readers=[InMemoryMetricReader()],
    )

    assert GLOBAL_CONFIG.service_version == '1.2.3'

    configure(
        token='abc',
        logfire_api_session=logfire_api_session,
        metric_readers=[InMemoryMetricReader()],
    )

    assert GLOBAL_CONFIG.service_version == git_sha

    dir = os.getcwd()

    try:
        os.chdir(tmp_path)
        configure(
            token='abc',
            logfire_api_session=logfire_api_session,
            metric_readers=[InMemoryMetricReader()],
        )
        assert GLOBAL_CONFIG.service_version is None
    finally:
        os.chdir(dir)


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
            processors=[SimpleSpanProcessor(exporter)],
            metric_readers=[InMemoryMetricReader()],
        )

    logfire.info('test1')

    # insert_assert(exporter.exported_spans_as_dict(include_resources=True))
    assert exporter.exported_spans_as_dict(include_resources=True) == [
        {
            'name': 'test1',
            'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
            'parent': None,
            'start_time': 1000000000,
            'end_time': 1000000000,
            'attributes': {
                'logfire.span_type': 'log',
                'logfire.level_name': 'info',
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
                }
            },
        }
    ]


def test_otel_otel_resource_attributes_env_var() -> None:
    time_generator = TimeGenerator()
    exporter = TestExporter()

    with patch.dict(os.environ, {'OTEL_RESOURCE_ATTRIBUTES': 'service.name=banana,service.version=1.2.3'}):
        configure(
            send_to_logfire=False,
            console=False,
            ns_timestamp_generator=time_generator,
            id_generator=IncrementalIdGenerator(),
            processors=[SimpleSpanProcessor(exporter)],
            metric_readers=[InMemoryMetricReader()],
        )

    logfire.info('test1')

    # insert_assert(exporter.exported_spans_as_dict(include_resources=True))
    assert exporter.exported_spans_as_dict(include_resources=True) == [
        {
            'name': 'test1',
            'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
            'parent': None,
            'start_time': 1000000000,
            'end_time': 1000000000,
            'attributes': {
                'logfire.span_type': 'log',
                'logfire.level_name': 'info',
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
                }
            },
        }
    ]


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
            processors=[SimpleSpanProcessor(exporter)],
            metric_readers=[InMemoryMetricReader()],
        )

    logfire.info('test1')

    # insert_assert(exporter.exported_spans_as_dict(include_resources=True))
    assert exporter.exported_spans_as_dict(include_resources=True) == [
        {
            'name': 'test1',
            'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
            'parent': None,
            'start_time': 1000000000,
            'end_time': 1000000000,
            'attributes': {
                'logfire.span_type': 'log',
                'logfire.level_name': 'info',
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
                }
            },
        }
    ]


def test_config_serializable():
    """
    Tests that by default, the logfire config can be serialized in the way that we do when sending it to another process.

    Here's an example of a configuration that (as of writing) fails to serialize:

        from opentelemetry.sdk.trace.export import SimpleSpanProcessor

        import logfire
        from logfire.exporters.console import SimpleConsoleSpanExporter
        from logfire.integrations._executors import serialize_config

        logfire.configure(processors=[SimpleSpanProcessor(SimpleConsoleSpanExporter())])

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
    )

    for field in dataclasses.fields(GLOBAL_CONFIG):
        # Check that the full set of dataclass fields is known.
        # If a new field appears here, make sure it gets deserialized properly in configure, and tested here.
        assert dataclasses.is_dataclass(getattr(GLOBAL_CONFIG, field.name)) == (
            field.name in ['pydantic_plugin', 'console']
        )

    serialized = serialize_config()
    deserialize_config(serialized)
    serialized2 = serialize_config()

    def normalize(s):
        for value in s.values():
            assert not dataclasses.is_dataclass(value)
        # These values get deepcopied by dataclasses.asdict, so we can't compare them directly
        return {k: v for k, v in s.items() if k not in ['logfire_api_session', 'id_generator']}

    assert normalize(serialized) == normalize(serialized2)

    assert isinstance(GLOBAL_CONFIG.pydantic_plugin, logfire.PydanticPlugin)
    assert isinstance(GLOBAL_CONFIG.console, logfire.ConsoleOptions)


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


def test_initialize_project_use_existing_project_no_projects(tmp_dir_cwd: Path, tmp_path: Path, capsys):
    os.environ['LOGFIRE_ANONYMOUS_PROJECT_ENABLED'] = 'false'

    auth_file = tmp_path / 'default.toml'
    auth_file.write_text(
        '[tokens."https://api.logfire.dev"]\ntoken = "fake_user_token"\nexpiration = "2099-12-31T23:59:59"'
    )
    with ExitStack() as stack:
        stack.enter_context(mock.patch('logfire._config.DEFAULT_FILE', auth_file))
        confirm_mock = stack.enter_context(mock.patch('rich.prompt.Confirm.ask', side_effect=[True, True]))
        stack.enter_context(mock.patch('rich.prompt.Prompt.ask', side_effect=['', 'myproject', '']))

        request_mocker = requests_mock.Mocker()
        stack.enter_context(request_mocker)
        request_mocker.get('https://api.logfire.dev/v1/projects/', json=[])
        request_mocker.get('https://api.logfire.dev/v1/organizations/', json=[{'organization_name': 'fake_org'}])
        create_project_response = {
            'json': {
                'project_name': 'myproject',
                'token': 'fake_token',
                'project_url': 'fake_project_url',
            }
        }
        request_mocker.post('https://api.logfire.dev/v1/projects/fake_org', [create_project_response])

        logfire.configure()

    assert confirm_mock.mock_calls == [
        call('The project will be created in the organization "fake_org". Continue?', default=True),
    ]


def test_initialize_project_use_existing_project(tmp_dir_cwd: Path, tmp_path: Path, capsys):
    os.environ['LOGFIRE_ANONYMOUS_PROJECT_ENABLED'] = 'false'

    auth_file = tmp_path / 'default.toml'
    auth_file.write_text(
        '[tokens."https://api.logfire.dev"]\ntoken = "fake_user_token"\nexpiration = "2099-12-31T23:59:59"'
    )
    with ExitStack() as stack:
        stack.enter_context(mock.patch('logfire._config.DEFAULT_FILE', auth_file))
        confirm_mock = stack.enter_context(mock.patch('rich.prompt.Confirm.ask', side_effect=[True, True]))
        prompt_mock = stack.enter_context(mock.patch('rich.prompt.Prompt.ask', side_effect=['1', '']))

        request_mocker = requests_mock.Mocker()
        stack.enter_context(request_mocker)
        request_mocker.get(
            'https://api.logfire.dev/v1/projects/',
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
            'https://api.logfire.dev/v1/organizations/fake_org/projects/fake_project/write-tokens/',
            [create_project_response],
        )

        logfire.configure()

    assert confirm_mock.mock_calls == [
        call('Do you want to use one of your existing projects? ', default=True),
    ]
    assert prompt_mock.mock_calls == [
        call(
            'Please select one of the existing project number:\n1. fake_org/fake_project\n', choices=['1'], default='1'
        ),
        call(
            'Project initialized successfully. You will be able to view it at: fake_project_url\nPress Enter to continue',
        ),
    ]
    assert capsys.readouterr().err == 'Logfire project URL: fake_project_url\n'

    assert json.loads((tmp_dir_cwd / '.logfire/logfire_credentials.json').read_text()) == {
        **create_project_response['json'],
        'logfire_api_url': 'https://api.logfire.dev',
    }


def test_initialize_project_create_project(tmp_dir_cwd: Path, tmp_path: Path, capsys):
    os.environ['LOGFIRE_ANONYMOUS_PROJECT_ENABLED'] = 'false'

    auth_file = tmp_path / 'default.toml'
    auth_file.write_text(
        '[tokens."https://api.logfire.dev"]\ntoken = "fake_user_token"\nexpiration = "2099-12-31T23:59:59"'
    )
    with ExitStack() as stack:
        stack.enter_context(mock.patch('logfire._config.DEFAULT_FILE', auth_file))
        confirm_mock = stack.enter_context(mock.patch('rich.prompt.Confirm.ask', side_effect=[False, True]))
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
        request_mocker.get('https://api.logfire.dev/v1/projects/', json=[])
        request_mocker.get('https://api.logfire.dev/v1/organizations/', json=[{'organization_name': 'fake_org'}])

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
                        'msg': 'The project name is reserved and cannot be used',
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
            'https://api.logfire.dev/v1/projects/fake_org',
            [
                create_existing_project_response,
                create_reserved_project_response,
                create_project_response,
            ],
        )

        logfire.configure()

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
            "\nThe project you've entered is invalid. Valid project names:\n"
            '  * may contain lowercase alphanumeric characters\n'
            '  * may contain single hyphens\n'
            '  * may not start or end with a hyphen\n\n'
            'Enter the project name you want to use:',
            default='testinitializeprojectcreate0',
        ),
        call(
            '\nA project with that name already exists. Please enter a different project name',
            default=...,
        ),
        call(
            '\nThe project name you entered is invalid:\n'
            'The project name is reserved and cannot be used\n'
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
        'logfire_api_url': 'https://api.logfire.dev',
    }


def test_initialize_project_create_project_default_organization(tmp_dir_cwd: Path, tmp_path: Path, capsys):
    os.environ['LOGFIRE_ANONYMOUS_PROJECT_ENABLED'] = 'false'

    auth_file = tmp_path / 'default.toml'
    auth_file.write_text(
        '[tokens."https://api.logfire.dev"]\ntoken = "fake_user_token"\nexpiration = "2099-12-31T23:59:59"'
    )
    with ExitStack() as stack:
        stack.enter_context(mock.patch('logfire._config.DEFAULT_FILE', auth_file))
        prompt_mock = stack.enter_context(
            mock.patch('rich.prompt.Prompt.ask', side_effect=['fake_org', 'mytestproject1', ''])
        )

        request_mocker = requests_mock.Mocker()
        stack.enter_context(request_mocker)
        request_mocker.get('https://api.logfire.dev/v1/projects/', json=[])
        request_mocker.get(
            'https://api.logfire.dev/v1/organizations/',
            json=[{'organization_name': 'fake_org'}, {'organization_name': 'fake_org1'}],
        )
        request_mocker.get(
            'https://api.logfire.dev/v1/account/me', json={'default_organization': {'organization_name': 'fake_org1'}}
        )

        create_project_response = {
            'json': {
                'project_name': 'myproject',
                'token': 'fake_token',
                'project_url': 'fake_project_url',
            }
        }
        request_mocker.post(
            'https://api.logfire.dev/v1/projects/fake_org',
            [create_project_response],
        )

        logfire.configure()

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
