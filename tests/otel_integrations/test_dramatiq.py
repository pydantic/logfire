# pyright: reportMissingImports=false, reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownParameterType=false, reportUnknownArgumentType=false, reportUntypedBaseClass=false, reportGeneralTypeIssues=false, reportInvalidTypeForm=false, reportAttributeAccessIssue=false, reportUntypedFunctionDecorator=false, reportFunctionMemberAccess=false, reportPrivateUsage=false, reportUnnecessaryTypeIgnoreComment=false

from __future__ import annotations

import importlib
import json
import threading
from collections.abc import Iterator
from types import MethodType
from typing import Any
from unittest import mock

import pytest
from opentelemetry import trace

import logfire
from logfire.testing import TestExporter

dramatiq = pytest.importorskip('dramatiq')
from dramatiq import Message, Worker  # noqa: E402
from dramatiq.broker import MessageProxy  # noqa: E402
from dramatiq.brokers.stub import StubBroker  # noqa: E402
from dramatiq.middleware import Middleware, SkipMessage  # noqa: E402


@pytest.fixture
def broker() -> Iterator[StubBroker]:
    result = StubBroker()
    result.emit_after('process_boot')
    result.declare_queue('default')
    dramatiq.set_broker(result)
    yield result
    result.close()


def spans(exporter: TestExporter) -> list[dict[str, object]]:
    return exporter.exported_spans_as_dict(parse_json_attributes=True)


def rendered_spans(exporter: TestExporter, message: str) -> list[dict[str, object]]:
    return [span for span in spans(exporter) if span['attributes'].get('logfire.msg') == message]  # type: ignore[union-attr]


def proxy(message: Message[Any]) -> MessageProxy:
    return MessageProxy(message)


def make_message(
    queue_name: str = 'default',
    actor_name: str = 'actor',
    *,
    kwargs: dict[str, object] | None = None,
    options: dict[str, Any] | None = None,
    message_id: str = 'id',
) -> Message[Any]:
    return Message(
        queue_name=queue_name,
        actor_name=actor_name,
        args=(),
        kwargs=kwargs or {},
        options=options or {},
        message_id=message_id,
        message_timestamp=0,
    )


def test_missing_dependency() -> None:
    import logfire._internal.integrations.dramatiq as integration

    with mock.patch.dict('sys.modules', {'dramatiq': None}):
        with pytest.raises(RuntimeError, match=r"pip install 'logfire\[dramatiq\]'"):
            importlib.reload(integration)
    importlib.reload(integration)


def test_stub_broker_worker_lifecycle_and_idempotency(broker: StubBroker, exporter: TestExporter) -> None:
    middleware = logfire.instrument_dramatiq(broker)
    assert isinstance(middleware, Middleware)
    assert logfire.instrument_dramatiq(broker) is middleware
    assert isinstance(broker.enqueue, MethodType)
    assert broker.enqueue.__self__ is broker

    received: list[str] = []
    worker_context_is_valid: list[bool] = []

    @dramatiq.actor(broker=broker)
    def greet(name: str) -> None:
        received.append(name)
        worker_context_is_valid.append(trace.get_current_span().get_span_context().is_valid)

    worker = Worker(broker, worker_timeout=50, worker_threads=1)
    worker.start()
    try:
        with logfire.span('request'):
            greet.send('world')
        broker.join(greet.queue_name, timeout=5_000)
    finally:
        worker.stop(timeout=5_000)

    assert received == ['world']
    # The consumer span is deliberately not attached as the worker's current context.
    assert worker_context_is_valid == [False]
    [request] = [span for span in spans(exporter) if span['name'] == 'request']
    [producer] = rendered_spans(exporter, 'greet send')
    [consumer] = rendered_spans(exporter, 'greet process')
    assert producer['name'] == '{message.actor_name} send'
    assert consumer['name'] == '{message.actor_name} process'
    assert producer['parent']['span_id'] == request['context']['span_id']  # type: ignore[index]
    assert consumer['parent']['span_id'] == producer['context']['span_id']  # type: ignore[index]
    assert consumer['attributes']['messaging.operation'] == 'process'  # type: ignore[index]


def test_default_and_nonempty_brokers(broker: StubBroker, exporter: TestExporter) -> None:
    broker.declare_queue('already-has-work')
    broker.enqueue(make_message('already-has-work', message_id='fixed-id'))
    middleware = logfire.instrument_dramatiq()
    assert middleware is logfire.instrument_dramatiq(broker)
    broker.declare_queue('other')
    broker.enqueue(make_message('other', message_id='second-id'))
    assert [span['attributes']['logfire.msg'] for span in spans(exporter)] == ['actor send']  # type: ignore[index]


def test_uninstrument_restores_broker(broker: StubBroker, exporter: TestExporter) -> None:
    original_enqueue = broker.enqueue
    middleware = logfire.instrument_dramatiq(broker)
    wrapped_enqueue = broker.enqueue

    middleware.uninstrument()
    middleware.uninstrument()
    assert broker.enqueue.__self__ is original_enqueue.__self__
    assert broker.enqueue.__func__ is original_enqueue.__func__
    assert wrapped_enqueue is not broker.enqueue
    assert middleware not in broker.middleware
    assert not hasattr(broker, '_logfire_dramatiq_middleware')

    broker.enqueue(make_message(message_id='without-span'))
    assert spans(exporter) == []
    replacement = logfire.instrument_dramatiq(broker)
    assert replacement is not middleware
    replacement.uninstrument()


def test_json_carriers_preserve_baggage_and_creation_link(broker: StubBroker, exporter: TestExporter) -> None:
    middleware = logfire.instrument_dramatiq(broker)
    message = make_message()
    with logfire.set_baggage(customer='acme'):
        broker.enqueue(message)

    original_creation = message.options['_logfire_creation_context']
    original_delivery = message.options['_logfire_delivery_context']
    creation = json.loads(original_creation)
    assert 'baggage' in creation and 'customer=acme' in creation['baggage']

    # A retry or queue move keeps the original creation carrier but gets a new delivery parent.
    broker.enqueue(message)
    assert message.options['_logfire_creation_context'] == original_creation
    assert message.options['_logfire_delivery_context'] != original_delivery
    assert 'customer=acme' in json.loads(message.options['_logfire_delivery_context'])['baggage']

    message_proxy = proxy(message)
    middleware.before_process_message(broker, message_proxy)
    middleware.after_process_message(broker, message_proxy)

    first_producer, second_producer = rendered_spans(exporter, 'actor send')
    [consumer] = rendered_spans(exporter, 'actor process')
    assert second_producer['parent']['span_id'] == first_producer['context']['span_id']  # type: ignore[index]
    assert second_producer.get('links', []) == []
    assert consumer['parent']['span_id'] == second_producer['context']['span_id']  # type: ignore[index]
    assert consumer['links'][0]['context']['span_id'] == first_producer['context']['span_id']  # type: ignore[index]
    assert consumer['links'][0]['attributes'] == {'messaging.dramatiq.context': 'creation'}  # type: ignore[index]


def test_enqueue_failure_restores_options(broker: StubBroker) -> None:
    def failing_enqueue(message: Message[Any], *, delay: int | None = None) -> Message[Any]:
        message.encode()
        raise AssertionError('the non-JSON argument should fail first')

    broker.enqueue = failing_enqueue  # type: ignore[method-assign]
    logfire.instrument_dramatiq(broker)

    missing = make_message(kwargs={'not_json': object()}, message_id='missing')
    with pytest.raises(Exception):
        broker.enqueue(missing)
    assert missing.options == {}

    existing_options = {
        '_logfire_creation_context': 'malformed-but-preserved',
        '_logfire_delivery_context': None,
    }
    existing = make_message(kwargs={'not_json': object()}, options=existing_options.copy(), message_id='existing')
    with pytest.raises(Exception):
        broker.enqueue(existing)
    assert existing.options == existing_options


def test_real_worker_retry_preserves_creation_and_updates_delivery(broker: StubBroker, exporter: TestExporter) -> None:
    middleware = logfire.instrument_dramatiq(broker)
    attempts: list[int] = []

    @dramatiq.actor(broker=broker, max_retries=1, min_backoff=1, max_backoff=1)
    def flaky() -> None:
        attempts.append(len(attempts) + 1)
        if len(attempts) == 1:
            raise ValueError('try again')

    worker = Worker(broker, worker_timeout=20, worker_threads=1)
    worker.start()
    try:
        flaky.send()
        broker.join(flaky.queue_name, timeout=5_000)
    finally:
        worker.stop(timeout=5_000)

    assert attempts == [1, 2]
    assert not middleware._active
    first_producer, retry_producer, redelivery_producer = rendered_spans(exporter, 'flaky send')
    first_consumer, second_consumer = rendered_spans(exporter, 'flaky process')
    assert first_consumer['parent']['span_id'] == first_producer['context']['span_id']  # type: ignore[index]
    assert first_consumer['events'][0]['name'] == 'exception'  # type: ignore[index]
    assert retry_producer['parent']['span_id'] == first_producer['context']['span_id']  # type: ignore[index]
    assert redelivery_producer['parent']['span_id'] == retry_producer['context']['span_id']  # type: ignore[index]
    assert second_consumer['parent']['span_id'] == redelivery_producer['context']['span_id']  # type: ignore[index]
    assert second_consumer['links'][0]['context']['span_id'] == first_producer['context']['span_id']  # type: ignore[index]


def test_real_worker_delayed_message(broker: StubBroker, exporter: TestExporter) -> None:
    logfire.instrument_dramatiq(broker)
    received: list[str] = []

    @dramatiq.actor(broker=broker)
    def delayed(value: str) -> None:
        received.append(value)

    worker = Worker(broker, worker_timeout=20, worker_threads=1)
    worker.start()
    try:
        delayed.send_with_options(args=('later',), delay=1)
        broker.join(delayed.queue_name, timeout=5_000)
    finally:
        worker.stop(timeout=5_000)

    assert received == ['later']
    producer, redelivery_producer = rendered_spans(exporter, 'delayed send')
    [consumer] = rendered_spans(exporter, 'delayed process')
    assert redelivery_producer['parent']['span_id'] == producer['context']['span_id']  # type: ignore[index]
    assert consumer['parent']['span_id'] == redelivery_producer['context']['span_id']  # type: ignore[index]


def test_real_worker_skip_lifecycle(broker: StubBroker, exporter: TestExporter) -> None:
    middleware = logfire.instrument_dramatiq(broker)

    @dramatiq.actor(broker=broker)
    def skipped() -> None:
        raise SkipMessage()

    worker = Worker(broker, worker_timeout=20, worker_threads=1)
    worker.start()
    try:
        skipped.send()
        broker.join(skipped.queue_name, fail_fast=False, timeout=5_000)
    finally:
        worker.stop(timeout=5_000)

    assert not middleware._active
    [consumer] = rendered_spans(exporter, 'skipped process')
    assert consumer.get('events', []) == []


def test_real_worker_failure_and_nack_lifecycle(broker: StubBroker, exporter: TestExporter) -> None:
    middleware = logfire.instrument_dramatiq(broker)

    @dramatiq.actor(broker=broker, max_retries=0)
    def failed() -> None:
        raise ValueError('broken')

    worker = Worker(broker, worker_timeout=20, worker_threads=1)
    worker.start()
    try:
        failed.send()
        broker.join(failed.queue_name, fail_fast=False, timeout=5_000)
    finally:
        worker.stop(timeout=5_000)

    assert not middleware._active
    assert len(broker.dead_letters_by_queue[failed.queue_name]) == 1
    [consumer] = rendered_spans(exporter, 'failed process')
    assert consumer['events'][0]['name'] == 'exception'  # type: ignore[index]


@pytest.mark.parametrize('terminal_hook', ['after_skip_message', 'after_nack'])
def test_terminal_hook_cleanup(broker: StubBroker, exporter: TestExporter, terminal_hook: str) -> None:
    middleware = logfire.instrument_dramatiq(broker)
    message = make_message()
    broker.enqueue(message)
    message_proxy = proxy(message)
    middleware.before_process_message(broker, message_proxy)
    getattr(middleware, terminal_hook)(broker, message_proxy)
    assert not middleware._active
    assert [span['attributes']['logfire.msg'] for span in spans(exporter)] == [  # type: ignore[index]
        'actor send',
        'actor process',
    ]


def test_close_ends_active_delivery(broker: StubBroker, exporter: TestExporter) -> None:
    middleware = logfire.instrument_dramatiq(broker)
    message = make_message()
    broker.enqueue(message)
    message_proxy = proxy(message)
    middleware.before_process_message(broker, message_proxy)
    middleware.after_worker_shutdown(broker, object())
    middleware.close()

    assert not middleware._active
    [consumer] = rendered_spans(exporter, 'actor process')
    assert consumer['events'][0]['name'] == 'exception'  # type: ignore[index]


def test_terminal_hook_only_finishes_on_starting_thread(broker: StubBroker) -> None:
    middleware = logfire.instrument_dramatiq(broker)
    message = make_message()
    broker.enqueue(message)
    message_proxy = proxy(message)
    middleware.before_process_message(broker, message_proxy)

    other_thread = threading.Thread(target=middleware.after_process_message, args=(broker, message_proxy))
    other_thread.start()
    other_thread.join(timeout=5)
    assert not other_thread.is_alive()
    assert len(middleware._active) == 1

    middleware.after_process_message(broker, message_proxy)
    assert not middleware._active


def test_real_worker_concurrent_duplicate_message_ids(broker: StubBroker, exporter: TestExporter) -> None:
    middleware = logfire.instrument_dramatiq(broker)
    ready = threading.Barrier(3)
    release = threading.Event()
    actor_threads: dict[str, int] = {}
    actor_threads_lock = threading.Lock()

    def block(label: str) -> None:
        with actor_threads_lock:
            actor_threads[label] = threading.get_ident()
        ready.wait(timeout=5)
        if not release.wait(timeout=5):
            raise RuntimeError('main thread did not release workers')

    @dramatiq.actor(broker=broker, actor_name='first', max_retries=0)
    def first() -> None:
        block('first')

    @dramatiq.actor(broker=broker, actor_name='second', max_retries=0)
    def second() -> None:
        block('second')

    first_message = first.message().copy(message_id='duplicate')
    second_message = second.message().copy(message_id='duplicate')
    worker = Worker(broker, worker_timeout=20, worker_threads=2)
    worker.start()
    try:
        broker.enqueue(first_message)
        broker.enqueue(second_message)
        ready.wait(timeout=5)

        active = list(middleware._active.items())
        assert len(active) == 2
        assert {key[1] for key, _ in active} == set(actor_threads.values())
        assert all(key[0] == id(delivery.proxy) for key, delivery in active)
        assert all(isinstance(delivery.proxy, MessageProxy) for _, delivery in active)
    finally:
        release.set()
        broker.join('default', fail_fast=False, timeout=5_000)
        worker.stop(timeout=5_000)

    assert not middleware._active
    for actor_name in ('first', 'second'):
        [producer] = rendered_spans(exporter, f'{actor_name} send')
        [consumer] = rendered_spans(exporter, f'{actor_name} process')
        assert producer['attributes']['messaging.message.id'] == 'duplicate'  # type: ignore[index]
        assert consumer['parent']['span_id'] == producer['context']['span_id']  # type: ignore[index]
