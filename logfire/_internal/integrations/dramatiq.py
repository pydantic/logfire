"""Dramatiq instrumentation implemented as native Dramatiq middleware."""

# pyright: reportMissingImports=false, reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownParameterType=false, reportUnknownArgumentType=false, reportUntypedBaseClass=false, reportGeneralTypeIssues=false, reportInvalidTypeForm=false, reportAttributeAccessIssue=false

from __future__ import annotations

import json
import threading
from collections.abc import Callable
from contextlib import nullcontext
from dataclasses import dataclass
from types import MethodType
from typing import Any

from opentelemetry import propagate, trace
from opentelemetry.trace import SpanKind

from ... import propagate as logfire_propagate
from ..main import Logfire, LogfireSpan
from ..utils import handle_internal_errors

try:
    import dramatiq
    from dramatiq import Broker, Message
    from dramatiq.broker import MessageProxy
    from dramatiq.middleware import Middleware, Retries
except ImportError as e:  # pragma: no cover
    raise RuntimeError(
        '`logfire.instrument_dramatiq()` requires the `dramatiq` package.\n'
        'You can install this with:\n'
        "    pip install 'logfire[dramatiq]'"
    ) from e

_CREATION = '_logfire_creation_context'
_DELIVERY = '_logfire_delivery_context'
_MARKER = '_logfire_dramatiq_middleware'
_ORIGINAL_ENQUEUE = '_logfire_dramatiq_original_enqueue'


def _encode_context() -> str:
    carrier: dict[str, str] = {}
    propagate.inject(carrier)
    # A string, rather than an arbitrary mapping, is portable across every Dramatiq encoder.
    return json.dumps(carrier, separators=(',', ':'), sort_keys=True)


def _decode_context(value: object) -> dict[str, str]:
    if not isinstance(value, str):
        return {}
    try:
        result = json.loads(value)
    except (TypeError, ValueError):
        return {}
    if not isinstance(result, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in result.items()):
        return {}
    return result


def _span_context(carrier: dict[str, str]) -> trace.SpanContext | None:
    with logfire_propagate.attach_context(carrier):
        span_context = trace.get_current_span().get_span_context()
    return span_context if span_context.is_valid else None


@dataclass
class _ActiveDelivery:
    # Keeping the proxy alive prevents Python from reusing its id for another in-flight delivery.
    proxy: MessageProxy
    span: LogfireSpan


class LogfireDramatiqMiddleware(Middleware):
    """Create producer and consumer spans for a Dramatiq broker."""

    def __init__(self, logfire_instance: Logfire, broker: Broker):
        self.logfire_instance = logfire_instance.with_settings(custom_scope_suffix='dramatiq')
        self.broker = broker
        self._active: dict[tuple[int, int], _ActiveDelivery] = {}
        self._lock = threading.Lock()
        self._original_enqueue: Callable[..., Message[Any]] | None = None
        self._wrapped_enqueue: Callable[..., Message[Any]] | None = None

    @staticmethod
    def _key(message: MessageProxy) -> tuple[int, int]:
        # Message ids may be duplicated, especially when a message is redelivered. Object and
        # thread identity keep simultaneous deliveries isolated without changing serialized data.
        return id(message), threading.get_ident()

    def before_process_message(self, broker: Broker, message: MessageProxy) -> None:
        delivery = _decode_context(message.options.get(_DELIVERY))
        creation = _decode_context(message.options.get(_CREATION))
        links = []
        creation_context = _span_context(creation)
        delivery_context = _span_context(delivery)
        if creation_context and creation_context != delivery_context:
            links.append((creation_context, {'messaging.dramatiq.context': 'creation'}))

        span = self.logfire_instance.span(
            f'{message.actor_name} process',
            _span_kind=SpanKind.CONSUMER,
            _links=links,
            **_attributes(message, 'process'),
        )
        # Starting under the delivery context establishes the parent without making the consumer
        # span current. Dramatiq may finish or cancel work from another thread, where detaching an
        # OpenTelemetry context token created here would be invalid.
        with logfire_propagate.attach_context(delivery):
            span._start()  # pyright: ignore[reportPrivateUsage]
        key = self._key(message)
        with self._lock:
            previous = self._active.pop(key, None)
            self._active[key] = _ActiveDelivery(message, span)
        if previous is not None:
            self._finish(previous, RuntimeError('Dramatiq started the same message delivery twice'))

    def after_process_message(
        self, broker: Broker, message: MessageProxy, *, result: Any = None, exception: BaseException | None = None
    ) -> None:
        self._finish_message(message, exception)

    def after_skip_message(self, broker: Broker, message: MessageProxy) -> None:
        self._finish_message(message, None)

    def after_nack(self, broker: Broker, message: MessageProxy) -> None:
        self._finish_message(message, None)

    def after_worker_shutdown(self, broker: Broker, worker: Any) -> None:
        self.close()

    def _finish_message(self, message: MessageProxy, exception: BaseException | None) -> None:
        with self._lock:
            active = self._active.pop(self._key(message), None)
        if active is not None:
            self._finish(active, exception)

    @staticmethod
    def _finish(active: _ActiveDelivery, exception: BaseException | None) -> None:
        if exception is not None:
            with handle_internal_errors:
                active.span.record_exception(exception, escaped=True)
        active.span._end()  # pyright: ignore[reportPrivateUsage]

    def close(self) -> None:
        """Finish deliveries left open by worker cancellation or shutdown."""
        with self._lock:
            deliveries = list(self._active.values())
            self._active.clear()
        for active in deliveries:
            self._finish(active, RuntimeError('Dramatiq worker stopped during message delivery'))

    def uninstrument(self) -> None:
        """Remove this middleware, restore the broker enqueue method, and finish active deliveries."""
        self.close()
        broker = self.broker
        if getattr(broker, _MARKER, None) is not self:
            return

        if self in broker.middleware:
            broker.middleware.remove(self)
        if self._original_enqueue is not None and broker.enqueue is self._wrapped_enqueue:
            broker.enqueue = self._original_enqueue
        if hasattr(broker, _ORIGINAL_ENQUEUE):
            delattr(broker, _ORIGINAL_ENQUEUE)
        delattr(broker, _MARKER)


def _attributes(message: Message[Any] | MessageProxy, operation: str) -> dict[str, Any]:
    return {
        'messaging.system': 'dramatiq',
        'messaging.operation': operation,
        'messaging.destination.name': message.queue_name,
        'messaging.message.id': message.message_id,
        'messaging.dramatiq.actor': message.actor_name,
    }


def _wrap_enqueue(broker: Broker, middleware: LogfireDramatiqMiddleware) -> None:
    original: Callable[..., Message[Any]] = broker.enqueue

    def enqueue(self: Broker, message: Message[Any], *, delay: int | None = None) -> Message[Any]:
        creation_was_missing = _CREATION not in message.options
        delivery_was_missing = _DELIVERY not in message.options
        old_creation = message.options.get(_CREATION)
        old_delivery = message.options.get(_DELIVERY)
        old_delivery_carrier = _decode_context(old_delivery)
        current_context = trace.get_current_span().get_span_context()
        old_delivery_context = _span_context(old_delivery_carrier)
        parent = (
            nullcontext()
            if current_context.is_valid or not old_delivery_carrier
            else logfire_propagate.attach_context(old_delivery_carrier)
        )
        effective_parent_context = current_context if current_context.is_valid else old_delivery_context
        creation_context = _span_context(_decode_context(old_creation))
        links = []
        if creation_context and creation_context != effective_parent_context:
            links.append((creation_context, {'messaging.dramatiq.context': 'creation'}))
        with (
            parent,
            middleware.logfire_instance.span(
                f'{message.actor_name} send',
                _span_kind=SpanKind.PRODUCER,
                _links=links,
                **_attributes(message, 'send'),
            ),
        ):
            if creation_was_missing:
                message.options[_CREATION] = _encode_context()
            message.options[_DELIVERY] = _encode_context()
            try:
                return original(message, delay=delay)
            except BaseException:
                if creation_was_missing:
                    message.options.pop(_CREATION, None)
                else:
                    message.options[_CREATION] = old_creation
                if delivery_was_missing:
                    message.options.pop(_DELIVERY, None)
                else:
                    message.options[_DELIVERY] = old_delivery
                raise

    setattr(broker, _ORIGINAL_ENQUEUE, original)
    wrapped = MethodType(enqueue, broker)
    broker.enqueue = wrapped
    middleware._original_enqueue = original  # pyright: ignore[reportPrivateUsage]
    middleware._wrapped_enqueue = wrapped  # pyright: ignore[reportPrivateUsage]


def instrument_dramatiq(logfire_instance: Logfire, broker: Broker | None = None) -> LogfireDramatiqMiddleware:
    """Instrument a Dramatiq broker, returning the installed middleware."""
    broker = broker if broker is not None else dramatiq.get_broker()
    existing = getattr(broker, _MARKER, None)
    if isinstance(existing, LogfireDramatiqMiddleware):
        return existing

    middleware = LogfireDramatiqMiddleware(logfire_instance, broker)
    # Adding after Retries makes our after hook run first, so the consumer span closes before
    # Dramatiq enqueues a retry.
    try:
        broker.add_middleware(middleware, after=Retries)
    except ValueError:
        broker.add_middleware(middleware)
    _wrap_enqueue(broker, middleware)
    setattr(broker, _MARKER, middleware)
    return middleware
