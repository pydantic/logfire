import sys
from typing import Any, Iterator

import pytest
from inline_snapshot import snapshot
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.trace import Span
from redis import Connection, Redis
from testcontainers.redis import RedisContainer

import logfire
from logfire.testing import TestExporter

# TODO find a better solution
pytestmark = pytest.mark.skipif(sys.version_info < (3, 9), reason='Redis testcontainers has problems in 3.8')


@pytest.fixture(scope='module', autouse=True)
def redis_container() -> Iterator[RedisContainer]:
    with RedisContainer('redis:latest') as redis:
        yield redis


@pytest.fixture
def redis(redis_container: RedisContainer):
    with redis_container.get_client() as redis:  # type: ignore
        yield redis


@pytest.fixture
def redis_port(redis_container: RedisContainer) -> str:
    return redis_container.get_exposed_port(6379)


@pytest.fixture(autouse=True)
def uninstrument_redis():
    try:
        yield
    finally:
        RedisInstrumentor().uninstrument()  # type: ignore


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
                    'net.peer.name': 'localhost',
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
                    'net.peer.name': 'localhost',
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
                    'net.peer.name': 'localhost',
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
                    'net.peer.name': 'localhost',
                    'net.peer.port': redis_port,
                    'net.transport': 'ip_tcp',
                    'db.redis.args_length': 3,
                    'potato': 'tomato',
                },
            }
        ]
    )
