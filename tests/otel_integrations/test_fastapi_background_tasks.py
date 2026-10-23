from __future__ import annotations

import asyncio
from threading import get_ident
from typing import Any

import pytest
from opentelemetry import baggage, context, trace
from opentelemetry.trace import Span, SpanContext
from starlette.background import BackgroundTask as StarletteBackgroundTask, BackgroundTasks as StarletteBackgroundTasks
from starlette.responses import Response
from starlette.testclient import TestClient
from starlette.types import Scope

pytest.importorskip('fastapi', reason='FastAPI requires pydantic>=2.7', exc_type=ImportError)

import fastapi
from fastapi import BackgroundTasks, FastAPI, WebSocket

import logfire
from logfire._internal.integrations.fastapi import (
    _TracedBackgroundTasks,  # pyright: ignore[reportPrivateUsage]
    instrument_fastapi,
)
from logfire._internal.utils import is_instrumentation_suppressed, suppress_instrumentation
from logfire.sampling import TailSamplingSpanInfo
from logfire.testing import TestExporter


@pytest.mark.parametrize('keep_request,keep_background', [(False, True), (False, False), (True, True), (True, False)])
def test_background_tasks_have_independent_tail_sampling(
    config_kwargs: dict[str, Any], exporter: TestExporter, keep_request: bool, keep_background: bool
) -> None:
    decisions: list[tuple[str, str, int]] = []
    ran: list[str] = []
    async_threads: list[int] = []
    sync_threads: list[int] = []
    request_contexts: list[SpanContext] = []
    background_trace_ids: set[int] = set()

    def tail(info: TailSamplingSpanInfo) -> float:
        assert info.span.context is not None
        trace_id = info.span.context.trace_id
        decisions.append((info.event, info.span.name, trace_id))
        if info.span.name == 'FastAPI background tasks':
            background_trace_ids.add(trace_id)
        return float(keep_background if trace_id in background_trace_ids else keep_request)

    def server_request_hook(span: Span, _scope: Scope) -> None:
        request_contexts.append(span.get_span_context())

    logfire.configure(**config_kwargs, sampling=logfire.SamplingOptions(tail=tail))
    app = FastAPI()

    async def async_callback(value: str) -> None:
        ran.append(value)
        async_threads.append(get_ident())
        with logfire.span('async callback'):
            logfire.info('async event')

    def sync_callback(value: str) -> str:
        ran.append(value)
        sync_threads.append(get_ident())
        with logfire.span('sync callback'):
            logfire.info('sync event')
        return 'ignored by Starlette'

    @app.get('/')
    async def endpoint(tasks: BackgroundTasks) -> dict[str, bool]:
        tasks.add_task(async_callback, 'async')
        tasks.add_task(sync_callback, 'sync')
        return {'ok': True}

    with logfire.instrument_fastapi(app, server_request_hook=server_request_hook):
        with TestClient(app) as client:
            assert client.get('/').json() == {'ok': True}

    assert ran == ['async', 'sync']
    assert len(async_threads) == len(sync_threads) == 1
    assert async_threads[0] != sync_threads[0]
    assert len(request_contexts) == 1
    request_context = request_contexts[0]
    spans = exporter.exported_spans_as_dict(include_instrumentation_scope=True)
    assert ('start', 'GET /', request_context.trace_id) in decisions

    if not keep_background:
        if keep_request:
            assert any(span['name'] == 'GET /' for span in spans)
            assert all(span['context']['trace_id'] == request_context.trace_id for span in spans)
        else:
            assert spans == []
        background_decisions = [
            (event, trace_id) for event, name, trace_id in decisions if name == 'FastAPI background tasks'
        ]
        assert len(background_decisions) == 2
        assert [event for event, _ in background_decisions] == ['start', 'end']
        assert all(trace_id != request_context.trace_id for _, trace_id in background_decisions)
        return

    roots = [span for span in spans if span['name'] == 'FastAPI background tasks']
    assert len(roots) == 1
    root = roots[0]
    assert root['context']['trace_id'] != request_context.trace_id
    assert root['parent'] is None
    assert root['end_time'] is not None
    assert root['links'] == [
        {
            'context': {
                'trace_id': request_context.trace_id,
                'span_id': request_context.span_id,
                'is_remote': request_context.is_remote,
            },
            'attributes': {},
        }
    ]

    request_roots = [span for span in spans if span['context']['trace_id'] == request_context.trace_id]
    assert bool(request_roots) == keep_request
    assert all(
        span['context']['trace_id'] == root['context']['trace_id'] for span in spans if span not in request_roots
    )

    background_spans = [span for span in spans if span['context']['trace_id'] == root['context']['trace_id']]
    by_id = {span['context']['span_id']: span for span in background_spans}
    assert {span['name'] for span in background_spans} >= {'async callback', 'sync callback'}
    assert all(span['end_time'] is not None for span in background_spans)
    for name in ('async callback', 'sync callback'):
        callback = next(span for span in background_spans if span['name'] == name)
        assert callback['parent'] is not None
        native_span = by_id[callback['parent']['span_id']]
        assert native_span['instrumentation_scope'] == 'opentelemetry.instrumentation.fastapi'
        assert native_span['parent']['span_id'] == root['context']['span_id']


def test_level_sampling_keeps_earlier_background_records_after_error(
    config_kwargs: dict[str, Any], exporter: TestExporter
) -> None:
    logfire.configure(
        **config_kwargs,
        sampling=logfire.SamplingOptions.level_or_duration(level_threshold='error', duration_threshold=None),
    )
    app = FastAPI()
    request_contexts: list[SpanContext] = []
    ran: list[str] = []

    def server_request_hook(span: Span, _scope: Scope) -> None:
        request_contexts.append(span.get_span_context())

    async def background() -> None:
        with logfire.span('before error span'):
            logfire.info('before error log')
        assert exporter.exported_spans_as_dict() == []
        logfire.error('background error')
        ran.append('completed')

    @app.get('/')
    async def endpoint(tasks: BackgroundTasks) -> dict[str, bool]:
        tasks.add_task(background)
        return {'ok': True}

    with logfire.instrument_fastapi(app, server_request_hook=server_request_hook):
        with TestClient(app) as client:
            assert client.get('/').json() == {'ok': True}

    assert ran == ['completed']
    assert len(request_contexts) == 1
    spans = exporter.exported_spans_as_dict()
    assert {span['name'] for span in spans} >= {
        'FastAPI background tasks',
        'before error span',
        'before error log',
        'background error',
    }
    root = next(span for span in spans if span['name'] == 'FastAPI background tasks')
    assert root['parent'] is None
    assert root['end_time'] is not None
    assert root['links'][0]['context'] == {
        'trace_id': request_contexts[0].trace_id,
        'span_id': request_contexts[0].span_id,
        'is_remote': request_contexts[0].is_remote,
    }
    assert all(span['context']['trace_id'] == root['context']['trace_id'] for span in spans)
    assert root['context']['trace_id'] != request_contexts[0].trace_id
    assert all(span['end_time'] is not None for span in spans)


@pytest.mark.parametrize('injected', [False, True])
def test_response_with_fastapi_background_tasks(injected: bool, exporter: TestExporter) -> None:
    app = FastAPI()
    ran: list[str] = []

    def callback(value: str) -> None:
        ran.append(value)
        logfire.info('response background event')

    def response(background: BackgroundTasks) -> Response:
        background.add_task(callback, 'once')
        return Response('ok', background=background)

    if injected:

        @app.get('/')
        async def endpoint_with_injection(tasks: BackgroundTasks) -> Response:
            return response(tasks)

    else:

        @app.get('/')
        async def endpoint_direct() -> Response:
            return response(BackgroundTasks())

    with logfire.instrument_fastapi(app):
        with TestClient(app) as client:
            assert client.get('/').text == 'ok'

    assert ran == ['once']
    spans = exporter.exported_spans_as_dict()
    request = next(span for span in spans if span['name'] == 'GET /')
    roots = [span for span in spans if span['name'] == 'FastAPI background tasks']
    assert len(roots) == 1
    root = roots[0]
    assert root['parent'] is None
    assert root['context']['trace_id'] != request['context']['trace_id']
    assert root['links'][0]['context'] == request['context']
    assert all(span['end_time'] is not None for span in spans)


@pytest.mark.parametrize('sync_failure', [False, True])
def test_background_failure_stops_later_tasks_and_closes_trace(exporter: TestExporter, sync_failure: bool) -> None:
    app = FastAPI()
    ran: list[str] = []

    def fail() -> None:
        ran.append('failing')
        raise ValueError('background failed')

    async def failing_async() -> None:
        fail()

    def skipped() -> None:
        ran.append('skipped')

    @app.get('/')
    async def endpoint(tasks: BackgroundTasks) -> str:
        tasks.add_task(fail if sync_failure else failing_async)
        tasks.add_task(skipped)
        return 'ok'

    with logfire.instrument_fastapi(app):
        with TestClient(app) as client, pytest.raises(ValueError, match='background failed'):
            client.get('/')

    assert ran == ['failing']
    spans = exporter.exported_spans_as_dict()
    roots = [span for span in spans if span['name'] == 'FastAPI background tasks']
    assert len(roots) == 1
    assert roots[0]['end_time'] is not None
    assert any(event['name'] == 'exception' for event in roots[0]['events'])


@pytest.mark.anyio
async def test_background_cancellation_restores_context(exporter: TestExporter) -> None:
    original = BackgroundTasks()
    custom_key = context.create_key('background-context-test')
    observed: list[tuple[object | None, object, int]] = []

    async def cancelled() -> None:
        observed.append(
            (
                baggage.get_baggage('request-baggage'),
                context.get_value(custom_key),
                trace.get_current_span().get_span_context().trace_id,
            )
        )
        raise asyncio.CancelledError()

    original.add_task(cancelled)
    with logfire.span('outer request'):
        outer_span = trace.get_current_span()
        outer_context = outer_span.get_span_context()
        request_context = context.set_value(custom_key, 'kept', baggage.set_baggage('request-baggage', 'present'))
        token = context.attach(request_context)
        try:
            with pytest.raises(asyncio.CancelledError):
                await _TracedBackgroundTasks(original, logfire.DEFAULT_LOGFIRE_INSTANCE, outer_context)()
            assert trace.get_current_span() is outer_span
            assert context.get_value(custom_key) == 'kept'
            assert baggage.get_baggage('request-baggage') == 'present'
        finally:
            context.detach(token)

    assert len(observed) == 1
    assert observed[0][:2] == ('present', 'kept')
    assert observed[0][2] != outer_context.trace_id
    roots = [span for span in exporter.exported_spans_as_dict() if span['name'] == 'FastAPI background tasks']
    assert len(roots) == 1
    assert roots[0]['end_time'] is not None


@pytest.mark.anyio
async def test_background_preserves_instrumentation_suppression(exporter: TestExporter) -> None:
    original = BackgroundTasks()
    observed: list[bool] = []

    async def callback() -> None:
        observed.append(is_instrumentation_suppressed())

    original.add_task(callback)
    with logfire.span('outer request'):
        outer_span = trace.get_current_span()
        with suppress_instrumentation():
            await _TracedBackgroundTasks(original, logfire.DEFAULT_LOGFIRE_INSTANCE, outer_span.get_span_context())()
            assert is_instrumentation_suppressed()
            assert trace.get_current_span() is outer_span

    assert observed == [True]
    assert not is_instrumentation_suppressed()
    assert not any(span['name'] == 'FastAPI background tasks' for span in exporter.exported_spans_as_dict())


@pytest.mark.parametrize('direct_response', [False, True])
def test_background_tasks_only_for_instrumented_requests(exporter: TestExporter, direct_response: bool) -> None:
    app = FastAPI()
    uninstrumented = FastAPI()
    ran: list[str] = []

    def callback(value: str) -> None:
        ran.append(value)

    async def endpoint(tasks: BackgroundTasks) -> Any:
        tasks.add_task(callback, 'ran')
        if direct_response:
            return Response('ok', background=tasks)
        return 'ok'

    app.get('/included')(endpoint)
    app.get('/excluded')(endpoint)
    uninstrumented.get('/plain')(endpoint)

    with logfire.instrument_fastapi(app, excluded_urls='/excluded'):
        with TestClient(app) as client:
            assert client.get('/excluded').status_code == 200
            assert not any(span['name'] == 'FastAPI background tasks' for span in exporter.exported_spans_as_dict())

            exporter.clear()
            assert client.get('/included').status_code == 200
            assert sum(span['name'] == 'FastAPI background tasks' for span in exporter.exported_spans_as_dict()) == 1

        exporter.clear()
        with TestClient(uninstrumented) as client:
            assert client.get('/plain').status_code == 200
            assert not any(span['name'] == 'FastAPI background tasks' for span in exporter.exported_spans_as_dict())

    assert ran == ['ran', 'ran', 'ran']


def test_empty_background_batch_does_not_start_trace(exporter: TestExporter) -> None:
    app = FastAPI()

    @app.get('/')
    async def endpoint(_tasks: BackgroundTasks) -> str:
        return 'ok'

    with logfire.instrument_fastapi(app):
        with TestClient(app) as client:
            assert client.get('/').status_code == 200

    assert not any(span['name'] == 'FastAPI background tasks' for span in exporter.exported_spans_as_dict())


@pytest.mark.parametrize('batch', [False, True])
def test_starlette_background_task_stays_outside_fastapi_batch_scope(exporter: TestExporter, batch: bool) -> None:
    app = FastAPI()
    ran: list[str] = []

    def callback() -> None:
        ran.append('ran')

    @app.get('/')
    async def endpoint() -> Response:
        if batch:
            background = StarletteBackgroundTasks()
            background.add_task(callback)
        else:
            background = StarletteBackgroundTask(callback)
        return Response('ok', background=background)

    with logfire.instrument_fastapi(app):
        with TestClient(app) as client:
            assert client.get('/').status_code == 200

    assert ran == ['ran']
    assert not any(span['name'] == 'FastAPI background tasks' for span in exporter.exported_spans_as_dict())


def test_global_fastapi_background_tasks(exporter: TestExporter) -> None:
    with instrument_fastapi(logfire.DEFAULT_LOGFIRE_INSTANCE):
        app = fastapi.FastAPI()

        @app.get('/')
        async def endpoint(tasks: BackgroundTasks) -> str:
            tasks.add_task(logfire.info, 'global background event')
            return 'ok'

        with TestClient(app) as client:
            assert client.get('/').status_code == 200

    spans = exporter.exported_spans_as_dict()
    request = next(span for span in spans if span['name'] == 'GET /')
    root = next(span for span in spans if span['name'] == 'FastAPI background tasks')
    assert root['parent'] is None
    assert root['links'][0]['context'] == request['context']


@pytest.mark.parametrize('direct_response', [False, True])
def test_background_trace_when_request_is_head_sampled_out(
    config_kwargs: dict[str, Any], exporter: TestExporter, direct_response: bool
) -> None:
    logfire.configure(**config_kwargs, sampling=logfire.SamplingOptions(head=0))
    app = FastAPI()
    request_contexts: list[SpanContext] = []
    callback_trace_ids: list[int] = []

    def server_request_hook(span: Span, _scope: Scope) -> None:
        request_contexts.append(span.get_span_context())

    async def callback() -> None:
        callback_trace_ids.append(trace.get_current_span().get_span_context().trace_id)

    @app.get('/')
    async def endpoint(tasks: BackgroundTasks) -> Any:
        tasks.add_task(callback)
        if direct_response:
            return Response('ok', background=tasks)
        return 'ok'

    with logfire.instrument_fastapi(app, server_request_hook=server_request_hook):
        with TestClient(app) as client:
            assert client.get('/').status_code == 200

    assert len(request_contexts) == len(callback_trace_ids) == 1
    assert callback_trace_ids[0] != request_contexts[0].trace_id
    assert exporter.exported_spans_as_dict() == []


def test_head_sampled_out_websocket_has_no_background_batch(
    config_kwargs: dict[str, Any], exporter: TestExporter
) -> None:
    logfire.configure(**config_kwargs, sampling=logfire.SamplingOptions(head=0))
    app = FastAPI()

    @app.websocket('/ws')
    async def endpoint(websocket: WebSocket) -> None:
        await websocket.accept()
        await websocket.send_text('ok')
        await websocket.close()

    with logfire.instrument_fastapi(app):
        with TestClient(app) as client, client.websocket_connect('/ws') as websocket:
            assert websocket.receive_text() == 'ok'

    assert exporter.exported_spans_as_dict() == []
