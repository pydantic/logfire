import importlib
import logging
from collections.abc import Iterator
from unittest import mock

import pytest
from celery import Celery
from celery.contrib.testing.worker import start_worker  # pyright: ignore[reportUnknownVariableType]
from celery.result import AsyncResult
from dirty_equals import IsInt, IsStr
from inline_snapshot import snapshot
from opentelemetry.instrumentation.celery import CeleryInstrumentor
from testcontainers.redis import RedisContainer

import logfire
import logfire._internal.integrations.celery
from logfire.testing import TestExporter


def test_missing_opentelemetry_dependency() -> None:
    with mock.patch.dict('sys.modules', {'opentelemetry.instrumentation.celery': None}):
        with pytest.raises(RuntimeError) as exc_info:
            importlib.reload(logfire._internal.integrations.celery)
        assert str(exc_info.value) == snapshot("""\
`logfire.instrument_celery()` requires the `opentelemetry-instrumentation-celery` package.
You can install this with:
    pip install 'logfire[celery]'\
""")


@pytest.fixture
def celery_app() -> Iterator[Celery]:
    with RedisContainer('redis:latest') as redis_container:
        redis_uri = f'redis://{redis_container.get_container_host_ip()}:{redis_container.get_exposed_port(6379)}/0'
        app = Celery('tasks', broker=redis_uri, backend=redis_uri)

        @app.task(name='tasks.say_hello')  # type: ignore
        def say_hello():  # type: ignore
            return 'hello'

        logfire.instrument_celery()
        try:
            yield app
        finally:
            CeleryInstrumentor().uninstrument()


def test_instrument_celery(celery_app: Celery, exporter: TestExporter) -> None:
    logger = logging.getLogger()
    with logfire.span('trace'), start_worker(celery_app, perform_ping_check=False, loglevel=logger.level):  # pyright: ignore[reportGeneralTypeIssues]
        for _ in range(3):
            exporter.clear()
            # Send and wait for the task to be executed
            result: AsyncResult = celery_app.send_task('tasks.say_hello')  # type: ignore
            value = result.get(timeout=10)  # type: ignore
            assert value == 'hello'
            result.backend = None

            # There are two spans:
            # 1. Trigger the task with `send_task`.
            # 2. Run the task.
            # The `run` span ends in the worker thread, so it can be exported late:
            # a previous iteration's `run` span may land after `exporter.clear()`, and
            # its position relative to the `apply_async` span is not deterministic.
            # Select spans by name rather than by position.
            spans = exporter.exported_spans_as_dict(parse_json_attributes=True)
            assert {span['name'] for span in spans} <= {'apply_async/tasks.say_hello', 'run/tasks.say_hello'}
            [apply_async_span] = [span for span in spans if span['name'] == 'apply_async/tasks.say_hello']
            assert apply_async_span == snapshot(
                {
                    'name': 'apply_async/tasks.say_hello',
                    'context': {'trace_id': 1, 'span_id': IsInt(), 'is_remote': False},
                    'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                    'start_time': IsInt(),
                    'end_time': IsInt(),
                    'attributes': {
                        'logfire.span_type': 'span',
                        'logfire.msg': 'apply_async/tasks.say_hello',
                        'celery.action': 'apply_async',
                        'messaging.message.id': IsStr(),
                        'celery.task_name': 'tasks.say_hello',
                        'messaging.destination_kind': 'queue',
                        'messaging.destination': 'celery',
                    },
                }
            )
            run_spans = [span for span in spans if span['name'] == 'run/tasks.say_hello']
            if run_spans:  # pragma: no branch
                assert run_spans[-1] == snapshot(
                    {
                        'name': 'run/tasks.say_hello',
                        'context': {'trace_id': 1, 'span_id': IsInt(), 'is_remote': False},
                        'parent': {'trace_id': 1, 'span_id': IsInt(), 'is_remote': True},
                        'start_time': IsInt(),
                        'end_time': IsInt(),
                        'attributes': {
                            'logfire.span_type': 'span',
                            'logfire.msg': 'run/tasks.say_hello',
                            'celery.action': 'run',
                            'celery.state': 'SUCCESS',
                            'messaging.conversation_id': IsStr(),
                            'messaging.destination': 'celery',
                            'celery.delivery_info': "{'exchange': '', 'routing_key': 'celery', 'priority': 0, 'redelivered': False}",
                            'messaging.message.id': IsStr(),
                            'celery.reply_to': IsStr(),
                            'celery.hostname': IsStr(),
                            'celery.task_name': 'tasks.say_hello',
                        },
                    },
                )
                break
        else:  # pragma: no cover
            pytest.fail('No spans found for the task execution')
