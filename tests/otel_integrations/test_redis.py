from __future__ import annotations

import importlib
import warnings
from collections.abc import Iterator
from typing import Any
from unittest import mock

import fakeredis
import pytest
from dirty_equals import IsStr
from inline_snapshot import snapshot
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.trace import Span
from redis import Connection, Redis

import logfire
import logfire._internal.integrations.redis
from logfire.testing import TestExporter


@pytest.fixture
def redis() -> Iterator[Redis]:
    # Create a fake Redis instance, suppressing the deprecation warning
    with warnings.catch_warnings():
        warnings.filterwarnings('ignore', category=DeprecationWarning)
        fake_redis = fakeredis.FakeRedis(decode_responses=True)
    yield fake_redis
    fake_redis.close()  # Clean up


@pytest.fixture
def redis_port() -> str:
    # Return a dummy port since we're using fakeredis
    return 6379  # pyright: ignore[reportReturnType]


@pytest.fixture(autouse=True)
def uninstrument_redis():
    try:
        yield
    finally:
        RedisInstrumentor().uninstrument()


def test_instrument_redis(redis: Redis, redis_port: str, exporter: TestExporter):
    logfire.instrument_redis()

    redis.set('my-key', 123)

    assert exporter.exported_spans_as_dict() == snapshot(
        [
            {
                'name': 'SET',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 2000000000,
                'attributes': {
                    'logfire.span_type': 'span',
                    'logfire.msg': 'SET ? ?',
                    'db.statement': 'SET ? ?',
                    'db.system': 'redis',
                    'db.redis.database_index': 0,
                    'net.peer.name': IsStr(),
                    'net.peer.port': redis_port,
                    'net.transport': 'ip_tcp',
                    'db.redis.args_length': 3,
                },
            }
        ]
    )


def test_instrument_redis_with_capture_statement(redis: Redis, redis_port: str, exporter: TestExporter):
    logfire.instrument_redis(capture_statement=True)

    redis.set('my-key', 123)

    assert exporter.exported_spans_as_dict() == snapshot(
        [
            {
                'name': 'SET',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 2000000000,
                'attributes': {
                    'logfire.span_type': 'span',
                    'logfire.msg': 'SET my-key 123',
                    'db.statement': 'SET my-key 123',
                    'db.system': 'redis',
                    'db.redis.database_index': 0,
                    'net.peer.name': IsStr(),
                    'net.peer.port': redis_port,
                    'net.transport': 'ip_tcp',
                    'db.redis.args_length': 3,
                },
            }
        ]
    )


def test_instrument_redis_with_big_capture_statement(redis: Redis, redis_port: str, exporter: TestExporter):
    logfire.instrument_redis(capture_statement=True)

    redis.set('k' * 100, 'x' * 1000)

    assert exporter.exported_spans_as_dict() == snapshot(
        [
            {
                'name': 'SET',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 2000000000,
                'attributes': {
                    'logfire.span_type': 'span',
                    'db.system': 'redis',
                    'db.redis.database_index': 0,
                    'net.peer.name': IsStr(),
                    'net.peer.port': redis_port,
                    'net.transport': 'ip_tcp',
                    'db.redis.args_length': 3,
                    'db.statement': 'SET kkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkk xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
                    'logfire.msg': 'SET kkkkkkkk...kkkkkkkk xxxxxxxx...xxxxxxxx',
                },
            }
        ]
    )


def test_instrument_redis_with_request_hook(redis: Redis, redis_port: str, exporter: TestExporter):
    def request_hook(span: Span, instance: Connection, *args: Any, **kwargs: Any) -> None:
        span.set_attribute('potato', 'tomato')

    logfire.instrument_redis(request_hook=request_hook, capture_statement=True)

    redis.set('my-key', 123)

    assert exporter.exported_spans_as_dict() == snapshot(
        [
            {
                'name': 'SET',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 2000000000,
                'attributes': {
                    'logfire.span_type': 'span',
                    'logfire.msg': 'SET my-key 123',
                    'db.statement': 'SET my-key 123',
                    'db.system': 'redis',
                    'db.redis.database_index': 0,
                    'net.peer.name': IsStr(),
                    'net.peer.port': redis_port,
                    'net.transport': 'ip_tcp',
                    'db.redis.args_length': 3,
                    'potato': 'tomato',
                },
            }
        ]
    )


def test_missing_opentelemetry_dependency() -> None:
    with mock.patch.dict('sys.modules', {'opentelemetry.instrumentation.redis': None}):
        with pytest.raises(RuntimeError) as exc_info:
            importlib.reload(logfire._internal.integrations.redis)
        assert str(exc_info.value) == snapshot("""\
`logfire.instrument_redis()` requires the `opentelemetry-instrumentation-redis` package.
You can install this with:
    pip install 'logfire[redis]'\
""")
