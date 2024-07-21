"""This module contains tests for the Celery integration.

To be able to run those tests, you need to have Redis running on localhost:6379.
We have a docker compose file that you can use to start Redis:

    ```bash
    docker compose up -d redis
    ```
"""

import logging
from typing import Iterator

import pytest
import redis
import redis.exceptions
from celery import Celery
from celery.contrib.testing.worker import start_worker
from celery.worker.worker import WorkController
from dirty_equals import IsStr
from inline_snapshot import snapshot
from opentelemetry.instrumentation.celery import CeleryInstrumentor

import logfire
from logfire.testing import TestExporter

pytestmark = [pytest.mark.integration]

try:
    client = redis.Redis()
    client.ping()  # type: ignore
except redis.exceptions.ConnectionError:  # pragma: no cover
    pytestmark.append(pytest.mark.skip('Redis is not running'))


@pytest.fixture
def celery_app() -> Iterator[Celery]:
    app = Celery('tasks', broker='redis://localhost:6379/0', backend='redis://localhost:6379/0')

    @app.task(name='tasks.say_hello')  # type: ignore
    def say_hello():  # type: ignore
        return 'hello'

    logfire.instrument_celery()
    try:
        yield app
    finally:
        CeleryInstrumentor().uninstrument()  # type: ignore


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
