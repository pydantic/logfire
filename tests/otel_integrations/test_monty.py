from __future__ import annotations

from typing import Any, cast

import anyio
import pydantic_monty
import pytest
from inline_snapshot import snapshot
from opentelemetry._logs import Logger, LogRecord, SeverityNumber
from opentelemetry.metrics import Meter
from opentelemetry.sdk._logs.export import SimpleLogRecordProcessor
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.metrics.view import View
from opentelemetry.trace import NonRecordingSpan, Tracer, get_current_span
from pydantic_monty import AsyncMonty, CollectString, Monty, MontyRuntimeError

import logfire
from logfire._internal.integrations import monty as monty_integration
from logfire._internal.integrations.monty import LogfireMontyLogger, LogfireMontyTracer
from logfire.testing import TestExporter, TestLogExporter, TimeGenerator, get_collected_metrics


def test_instrument_monty_dependency_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(monty_integration, '_installed', False)
    monkeypatch.delattr(pydantic_monty, 'instrument_telemetry')

    with pytest.raises(ImportError) as exc_info:
        monty_integration.instrument_monty(logfire.DEFAULT_LOGFIRE_INSTANCE)
    assert str(exc_info.value) == snapshot(
        '`logfire.instrument_monty()` requires a version of the `pydantic-monty` package '
        'which supports OpenTelemetry instrumentation.'
    )


def test_instrument_monty_passes_standard_components(
    monkeypatch: pytest.MonkeyPatch, config_kwargs: dict[str, Any]
) -> None:
    logfire.configure(**config_kwargs, metrics=False)
    received: dict[str, Any] = {}

    def instrument_telemetry(**kwargs: Any) -> None:
        received.update(kwargs)

    monkeypatch.setattr(monty_integration, '_installed', False)
    monkeypatch.setattr(pydantic_monty, 'instrument_telemetry', instrument_telemetry)
    monty_integration.instrument_monty(logfire.DEFAULT_LOGFIRE_INSTANCE)
    assert isinstance(received['tracer'], Tracer)
    assert isinstance(received['meter'], Meter)
    assert isinstance(received['logger'], Logger)


def test_logfire_standard_component_shims(
    exporter: TestExporter, time_generator: TimeGenerator, config_kwargs: dict[str, Any]
) -> None:
    logs_exporter = TestLogExporter(time_generator)
    config_kwargs['advanced'].log_record_processors = [SimpleLogRecordProcessor(logs_exporter)]
    logfire.configure(**config_kwargs, min_level='error')
    scoped = logfire.DEFAULT_LOGFIRE_INSTANCE.with_trace_sample_rate(0.5).with_settings(
        tags=['monty', 'existing'], console_log=False
    )
    tracer = LogfireMontyTracer(scoped)

    with logfire.span('parent'):
        rejected = tracer.start_span('too quiet', attributes={'logfire.level_num': 9})
        assert isinstance(rejected, NonRecordingSpan)
        assert rejected.get_span_context() == get_current_span().get_span_context()

        with tracer.start_as_current_span(
            'session {script_name}',
            attributes=cast(Any, {'script_name': 'test.py', 'logfire.level_num': 17, 'logfire.tags': ('existing', 1)}),
        ):
            pass

    spans = exporter.exported_spans_as_dict()
    assert [span['name'] for span in spans] == ['session {script_name}', 'parent']
    assert spans[0]['parent'] == spans[1]['context']
    assert spans[0]['attributes'] == snapshot(
        {
            'script_name': 'test.py',
            'logfire.level_num': 17,
            'logfire.tags': ('existing', 'monty'),
            'logfire.msg_template': 'session {script_name}',
            'logfire.msg': 'session test.py',
            'logfire.sample_rate': 0.5,
            'logfire.span_type': 'span',
        }
    )

    logger = LogfireMontyLogger(scoped.config.get_logger_provider().get_logger('test'), scoped)
    logger.emit(LogRecord(body=123, attributes={'logfire.tags': 'invalid'}))
    logger.emit(body='too quiet', severity_number=SeverityNumber.INFO)
    logger.emit(body='error', severity_number=SeverityNumber.ERROR)
    assert [
        {'body': record['body'], 'attributes': record['attributes']}
        for record in logs_exporter.exported_logs_as_dicts()
    ] == snapshot(
        [
            {'body': 123, 'attributes': {'logfire.tags': ('monty', 'existing'), 'logfire.disable_console_log': True}},
            {
                'body': 'error',
                'attributes': {
                    'logfire.msg_template': 'error',
                    'logfire.msg': 'error',
                    'logfire.level_num': 17,
                    'logfire.tags': ('monty', 'existing'),
                    'logfire.disable_console_log': True,
                },
            },
        ]
    )


def test_instrument_monty(exporter: TestExporter, logs_exporter: TestLogExporter) -> None:
    logfire.instrument_monty()
    output = CollectString()

    with logfire.span('parent'):
        with Monty() as pool:
            with pool.checkout(script_name='calculation.py') as session:
                assert session.feed_run("print('hello')\n1 + 2", print_callback=output) == 3

    assert output.output == 'hello\n'
    spans = exporter.exported_spans_as_dict(parse_json_attributes=True)
    assert [
        {
            'name': span['name'],
            'context': span['context'],
            'parent': span['parent'],
            'message': span['attributes']['logfire.msg'],
        }
        for span in spans
    ] == snapshot(
        [
            {
                'name': 'run code',
                'context': {'trace_id': 1, 'span_id': 5, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
                'message': 'run code',
            },
            {
                'name': 'session {script_name}',
                'context': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'message': 'session calculation.py',
            },
            {
                'name': 'parent',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'message': 'parent',
            },
        ]
    )
    assert spans[0]['attributes']['code'] == snapshot("print('hello')\n1 + 2")
    assert spans[0]['attributes']['output'] == snapshot(3)
    assert spans[1]['attributes']['script_name'] == snapshot('calculation.py')

    [printed] = logs_exporter.exported_logs_as_dicts()
    assert printed['body'] == snapshot('print stdout')
    assert printed['severity_number'] == snapshot(9)
    assert printed['trace_id'] == snapshot(1)
    assert printed['span_id'] == snapshot(5)
    assert printed['attributes']['text'] == snapshot('hello\n')
    assert printed['attributes']['logfire.msg_template'] == snapshot('print stdout')
    assert printed['attributes']['logfire.msg'] == snapshot('print stdout')
    assert printed['attributes']['logfire.level_num'] == snapshot(9)


def test_instrument_monty_sampling(exporter: TestExporter, config_kwargs: dict[str, Any]) -> None:
    logfire.configure(**config_kwargs, sampling=logfire.SamplingOptions(head=0))
    logfire.instrument_monty()

    with Monty() as pool:
        with pool.checkout() as session:
            assert session.feed_run('6 * 7') == 42

    assert exporter.exported_spans == snapshot([])


def test_instrument_monty_is_idempotent(exporter: TestExporter) -> None:
    logfire.instrument_monty()
    logfire.instrument_monty()

    with Monty() as pool:
        with pool.checkout() as session:
            assert session.feed_run('6 * 7') == 42

    assert [span['name'] for span in exporter.exported_spans_as_dict()] == snapshot(
        ['run code', 'session {script_name}']
    )


def test_instrument_monty_metrics(metrics_reader: InMemoryMetricReader) -> None:
    logfire.instrument_monty()

    with Monty(min_processes=1, max_processes=1) as pool:
        with pool.checkout() as session:
            assert session.feed_run('1 + 2') == 3

    metrics = get_collected_metrics(metrics_reader)
    names = {metric['name'] for metric in metrics}
    assert {
        'monty.pool.checkout.wait',
        'monty.pool.session.duration',
        'monty.pool.worker.terminated',
        'monty.pool.workers.idle',
        'monty.pool.workers.live',
        'monty.run.duration',
        'monty.run.execution_time',
        'monty.turn.duration',
        'monty.wire.frame.bytes',
    } <= names

    run = next(metric for metric in metrics if metric['name'] == 'monty.run.duration')
    assert run['description'] == snapshot('Wall time of one feed, including time spent waiting on the host.')
    assert run['unit'] == snapshot('s')
    assert run['data']['data_points'][0]['attributes'] == snapshot({'outcome': 'complete'})


def test_instrument_monty_metrics_use_host_views(config_kwargs: dict[str, Any]) -> None:
    metrics_reader = InMemoryMetricReader()
    logfire.configure(
        **config_kwargs,
        metrics=logfire.MetricsOptions(
            additional_readers=[metrics_reader],
            views=[View(instrument_name='monty.run.duration', name='monty.custom.run.duration')],
        ),
    )
    logfire.instrument_monty()

    with Monty() as pool:
        with pool.checkout() as session:
            assert session.feed_run('1 + 2') == 3

    names = {metric['name'] for metric in get_collected_metrics(metrics_reader)}
    assert 'monty.custom.run.duration' in names
    assert 'monty.run.duration' not in names


@pytest.fixture(params=['await fetch()', 'pending = fetch()\nawait pending'])
async def monty_async_callback_spans(exporter: TestExporter, request: pytest.FixtureRequest) -> dict[str, Any]:
    logfire.instrument_monty()

    async def fetch() -> int:
        with logfire.span('host callback'):
            await anyio.sleep(0)
            logfire.info('after await')
        return 42

    with logfire.span('parent'):
        async with AsyncMonty() as pool:
            async with pool.checkout() as session:
                assert await session.feed_run(request.param, external_lookup={'fetch': fetch}) == 42

    return {span['name']: span for span in exporter.exported_spans_as_dict(parse_json_attributes=True)}


@pytest.mark.anyio
async def test_instrument_monty_async_callback(monty_async_callback_spans: dict[str, Any]) -> None:
    spans = monty_async_callback_spans
    assert spans['session {script_name}']['parent'] == spans['parent']['context']
    assert spans['run code']['parent'] == spans['session {script_name}']['context']
    assert spans['call {function_name}']['parent'] == spans['run code']['context']
    assert spans['after await']['parent'] == spans['host callback']['context']
    assert spans['call {function_name}']['attributes']['function_name'] == 'fetch'
    assert spans['run code']['attributes']['output'] == 42


@pytest.mark.anyio
@pytest.mark.xfail(reason='Monty 0.0.23 lacks callback context propagation', raises=AssertionError, strict=True)
async def test_instrument_monty_async_callback_parent(monty_async_callback_spans: dict[str, Any]) -> None:
    spans = monty_async_callback_spans
    assert spans['host callback']['parent'] == spans['call {function_name}']['context']


@pytest.fixture
def monty_callback_exception_spans(exporter: TestExporter) -> dict[str, Any]:
    logfire.instrument_monty()

    def fail() -> None:
        raise ValueError('host failed')

    with Monty() as pool:
        with pool.checkout() as session:
            with pytest.raises(MontyRuntimeError, match='host failed'):
                session.feed_run('fail()', external_lookup={'fail': fail})

    return {span['name']: span for span in exporter.exported_spans_as_dict(parse_json_attributes=True)}


def test_instrument_monty_callback_exception(
    monty_callback_exception_spans: dict[str, Any], logs_exporter: TestLogExporter
) -> None:
    call = monty_callback_exception_spans['call {function_name}']
    run = monty_callback_exception_spans['run code']
    assert call['parent'] == run['context']
    assert call['attributes']['return_value'] == snapshot('raise ValueError: host failed')
    [error] = logs_exporter.exported_logs_as_dicts()
    assert error['body'] == snapshot('error ValueError')
    assert error['severity_number'] == 17
    assert {
        key: error['attributes'][key] for key in ('exc_type', 'exc_message', 'traceback', 'logfire.level_num')
    } == snapshot(
        {
            'exc_type': 'ValueError',
            'exc_message': 'host failed',
            'traceback': '<python-input-0>:1 in <module>',
            'logfire.level_num': 17,
        }
    )
    assert error['trace_id'] == run['context']['trace_id']
    assert error['span_id'] == run['context']['span_id']


@pytest.mark.xfail(reason='Monty 0.0.23 lacks callback exception events', raises=AssertionError, strict=True)
def test_instrument_monty_callback_exception_event(monty_callback_exception_spans: dict[str, Any]) -> None:
    call = monty_callback_exception_spans['call {function_name}']
    assert [event['attributes'] for event in call.get('events', [])] == snapshot(
        [
            {
                'exception.type': 'ValueError',
                'exception.message': 'host failed',
                'exception.stacktrace': 'ValueError: host failed',
                'exception.escaped': 'False',
            }
        ]
    )


def test_instrument_monty_scrubbing(exporter: TestExporter, logs_exporter: TestLogExporter) -> None:
    logfire.instrument_monty()
    output = CollectString()
    secret = 'example-private-value'

    def fetch(password: str) -> dict[str, Any]:
        return {'password': password, 'answer': 42}

    with Monty() as pool:
        with pool.checkout() as session:
            assert session.feed_run(
                'result = fetch(password=password)\nprint(result)\nresult',
                inputs={'password': secret},
                external_lookup={'fetch': fetch},
                print_callback=output,
            ) == {'password': secret, 'answer': 42}

    assert secret in output.output
    spans = exporter.exported_spans_as_dict(parse_json_attributes=True)
    logs = logs_exporter.exported_logs_as_dicts()
    assert secret not in repr(spans)
    assert secret not in repr(logs)
    assert [
        {
            'name': span['name'],
            'attributes': {
                key: value
                for key, value in span['attributes'].items()
                if key in {'inputs', 'kwargs', 'return_value', 'output'}
            },
        }
        for span in spans
    ] == snapshot(
        [
            {
                'name': 'call {function_name}',
                'attributes': {
                    'kwargs': {'password': "[Scrubbed due to 'password']"},
                    'return_value': {'password': "[Scrubbed due to 'password']", 'answer': 42},
                },
            },
            {
                'name': 'run code',
                'attributes': {
                    'inputs': {'password': "[Scrubbed due to 'password']"},
                    'output': {'password': "[Scrubbed due to 'password']", 'answer': 42},
                },
            },
            {'name': 'session {script_name}', 'attributes': {}},
        ]
    )
    assert [(record['body'], record['attributes']['text']) for record in logs] == snapshot(
        [('print stdout', "[Scrubbed due to 'password']")]
    )
