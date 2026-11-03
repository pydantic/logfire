from __future__ import annotations

import asyncio
import contextvars
import importlib
import inspect
import sys
from collections.abc import Iterator
from typing import Any
from unittest import mock

import pytest
from arq.connections import RedisSettings, create_pool
from arq.cron import CronJob
from arq.worker import Function, Worker, func
from opentelemetry import trace
from opentelemetry.instrumentation.arq import ArqInstrumentor
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from testcontainers.redis import RedisContainer

import logfire
from logfire._internal.integrations import arq as arq_integration
from logfire.testing import TestExporter


@pytest.fixture(autouse=True)
def uninstrument_arq() -> Iterator[None]:
    missing = object()
    originals = {cls: inspect.getattr_static(cls, 'coroutine', missing) for cls in (Function, CronJob)}
    try:
        yield
    finally:
        instrumentor = ArqInstrumentor()
        if instrumentor.is_instrumented_by_opentelemetry:
            instrumentor.uninstrument()
        # The community instrumentor leaves these descriptors behind when uninstrumenting.
        for cls, original in originals.items():
            if original is missing:
                if 'coroutine' in vars(cls):
                    delattr(cls, 'coroutine')
            else:
                setattr(cls, 'coroutine', original)


@pytest.mark.anyio
async def test_arq_jobs_keep_results_errors_and_distributed_parents(
    redis_container: RedisContainer, exporter: TestExporter, config_kwargs: dict[str, Any]
) -> None:
    local_exporter = TestExporter()
    config_kwargs['additional_span_processors'] = [SimpleSpanProcessor(local_exporter)]
    local_logfire = logfire.configure(local=True, **config_kwargs)
    local_logfire.instrument_arq()

    async def succeeds(ctx: dict[str, Any], *, value: int) -> int:
        with local_logfire.span('inside job'):
            return value + 1

    async def fails(ctx: dict[str, Any]) -> None:
        raise ValueError('job failed')

    queue = 'arq:queue:logfire-test'
    redis = await create_pool(
        RedisSettings(
            host=redis_container.get_container_host_ip(),
            port=int(redis_container.get_exposed_port(6379)),
        )
    )
    worker = Worker(
        [func(succeeds, name='succeeds'), func(fails, name='fails')],
        redis_pool=redis,
        queue_name=queue,
        burst=True,
        max_jobs=1,
        handle_signals=False,
    )
    try:
        with local_logfire.span('enqueue jobs'):
            root_context = trace.get_current_span().get_span_context()
            success = await redis.enqueue_job('succeeds', value=7, _job_id='success', _queue_name=queue)
            failure = await redis.enqueue_job('fails', _job_id='failure', _queue_name=queue)
        assert success is not None and failure is not None

        # A worker in another process cannot inherit the producer's ambient context.
        task = contextvars.Context().run(asyncio.create_task, worker.async_run())
        await asyncio.wait_for(task, timeout=10)
        assert await success.result(timeout=1) == 8
        with pytest.raises(ValueError):
            await failure.result(timeout=1)
    finally:
        await redis.aclose(close_connection_pool=True)

    spans = [
        span
        for span in local_exporter.exported_spans
        if span.attributes is not None and span.attributes.get('logfire.span_type') != 'pending_span'
    ]
    for job_id in ('success', 'failure'):
        producer = next(
            span
            for span in spans
            if span.kind == trace.SpanKind.CLIENT and (span.attributes or {}).get('arq.job.id') == job_id
        )
        consumer = next(
            span
            for span in spans
            if span.kind == trace.SpanKind.SERVER and (span.attributes or {}).get('arq.job.id') == job_id
        )
        assert producer.context is not None and consumer.context is not None
        assert producer.attributes is not None
        assert producer.parent is not None and producer.parent.span_id == root_context.span_id
        assert consumer.parent is not None and consumer.parent.span_id == producer.context.span_id
        assert consumer.context.trace_id == producer.context.trace_id == root_context.trace_id
        assert producer.attributes['arq.job.queue'] == queue

    succeeded = next(
        span
        for span in spans
        if span.kind == trace.SpanKind.SERVER and (span.attributes or {}).get('arq.job.id') == 'success'
    )
    child = next(span for span in spans if span.name == 'inside job')
    assert succeeded.context is not None
    assert child.parent is not None and child.parent.span_id == succeeded.context.span_id
    failed = next(
        span
        for span in spans
        if span.kind == trace.SpanKind.SERVER and (span.attributes or {}).get('arq.job.id') == 'failure'
    )
    assert failed.status.status_code == trace.StatusCode.ERROR
    exception = next(event for event in failed.events if event.name == 'exception')
    assert exception.attributes is not None
    assert exception.attributes['exception.type'] == 'ValueError'
    stacktrace = exception.attributes['exception.stacktrace']
    assert isinstance(stacktrace, str)
    assert 'ValueError: job failed' in stacktrace
    assert 'in fails' in stacktrace
    assert exporter.exported_spans == []


def test_missing_arq_instrumentation_dependency() -> None:
    try:
        with mock.patch.dict(sys.modules, {'opentelemetry.instrumentation.arq': None}):
            with pytest.raises(RuntimeError):
                importlib.reload(arq_integration)
    finally:
        importlib.reload(arq_integration)


def test_transitive_arq_import_error_is_not_masked() -> None:
    try:
        with mock.patch.dict(sys.modules, {'arq.worker': None}):
            del sys.modules['opentelemetry.instrumentation.arq']
            with pytest.raises(ModuleNotFoundError) as exc_info:
                importlib.reload(arq_integration)
            assert exc_info.value.name == 'arq.worker'
    finally:
        importlib.reload(arq_integration)
