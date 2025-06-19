import importlib
import logging
import warnings
from collections.abc import Iterator
from unittest import mock

import fakeredis
import pytest
from celery import Celery
from celery.contrib.testing.worker import start_worker
from celery.worker.worker import WorkController
from dirty_equals import IsStr
from inline_snapshot import snapshot
from opentelemetry.instrumentation.celery import CeleryInstrumentor

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
    # Create a fake Redis instance, suppressing the deprecation warning
    with warnings.catch_warnings():
        warnings.filterwarnings('ignore', category=DeprecationWarning)
        fake_redis = fakeredis.FakeStrictRedis()
    app = Celery('tasks')
    app.conf.update(  # type: ignore[attr-defined]
        broker_url='memory://',
        result_backend='redis://',
        broker_transport_options={'client': fake_redis},
        result_backend_transport_options={'client': fake_redis},
    )

    @app.task(name='tasks.say_hello')  # type: ignore
    def say_hello():  # type: ignore
        return 'hello'

    # Monkey patch Redis connection to use our fake Redis
    with mock.patch('redis.StrictRedis', return_value=fake_redis):
        logfire.instrument_celery()
        try:
            yield app
        finally:
            CeleryInstrumentor().uninstrument()


@pytest.fixture(autouse=True)
def celery_worker(celery_app: Celery) -> Iterator[WorkController]:
    logger = logging.getLogger()
    with start_worker(celery_app, perform_ping_check=False, loglevel=logger.level) as worker:  # type: ignore
        yield worker


def test_instrument_celery(celery_app: Celery, exporter: TestExporter) -> None:
    # Send and wait for the task to be executed
    result = celery_app.send_task('tasks.say_hello')  # type: ignore
    value = result.get(timeout=10)  # type: ignore
    assert value == 'hello'

    # There are two spans:
    # 1. Trigger the task with `send_task`.
    # 2. Run the task.
    assert exporter.exported_spans_as_dict() == snapshot(
        [
            {
                'name': 'apply_async/tasks.say_hello',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 2000000000,
                'attributes': {
                    'logfire.span_type': 'span',
                    'logfire.msg': 'apply_async/tasks.say_hello',
                    'celery.action': 'apply_async',
                    'messaging.message.id': IsStr(),
                    'celery.task_name': 'tasks.say_hello',
                    'messaging.destination_kind': 'queue',
                    'messaging.destination': 'celery',
                },
            },
            {
                'name': 'run/tasks.say_hello',
                'context': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': True},
                'start_time': 3000000000,
                'end_time': 4000000000,
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
        ]
    )
