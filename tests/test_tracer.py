from __future__ import annotations

import threading
from collections.abc import Callable

from opentelemetry.sdk.trace import TracerProvider as SDKTracerProvider

from logfire._internal.config import GLOBAL_CONFIG
from logfire._internal.tracer import ProxyTracerProvider


def _returns_within(action: Callable[[], object], seconds: float = 5.0) -> bool:
    """Run `action` in a thread and report whether it finished before `seconds`."""
    thread = threading.Thread(target=action, daemon=True)
    thread.start()
    thread.join(seconds)
    return not thread.is_alive()


def test_force_flush_does_not_deadlock_when_an_exporter_reads_the_resource() -> None:
    # An exporter may read `get_tracer_provider().resource` while it exports, which is
    # `ProxyTracerProvider.resource` and takes the proxy lock. The flush runs the exporter,
    # so it must not hold that lock (https://github.com/pydantic/logfire/issues/2789).
    proxy = ProxyTracerProvider(SDKTracerProvider(), GLOBAL_CONFIG)

    class ResourceReadingProvider(SDKTracerProvider):
        def force_flush(self, timeout_millis: int = 30000) -> bool:
            proxy.resource
            return True

    proxy.set_provider(ResourceReadingProvider())

    assert _returns_within(proxy.force_flush)


def test_shutdown_does_not_deadlock_when_an_exporter_reads_the_resource() -> None:
    proxy = ProxyTracerProvider(SDKTracerProvider(), GLOBAL_CONFIG)

    class ResourceReadingProvider(SDKTracerProvider):
        def shutdown(self) -> None:
            proxy.resource

    proxy.set_provider(ResourceReadingProvider())

    assert _returns_within(proxy.shutdown)


def test_shutdown_waits_for_an_in_flight_flush() -> None:
    # Releasing the lock must not let shutdown run against a provider that is still flushing.
    proxy = ProxyTracerProvider(SDKTracerProvider(), GLOBAL_CONFIG)
    flush_started = threading.Event()
    release_flush = threading.Event()
    shutdown_started = threading.Event()

    class SlowProvider(SDKTracerProvider):
        def force_flush(self, timeout_millis: int = 30000) -> bool:
            flush_started.set()
            release_flush.wait(5)
            return True

        def shutdown(self) -> None:
            shutdown_started.set()

    proxy.set_provider(SlowProvider())
    flush_thread = threading.Thread(target=proxy.force_flush, daemon=True)
    flush_thread.start()
    assert flush_started.wait(2)

    shutdown_entered = threading.Event()

    def shutdown() -> None:
        shutdown_entered.set()
        proxy.shutdown()

    shutdown_thread = threading.Thread(target=shutdown, daemon=True)
    shutdown_thread.start()
    assert shutdown_entered.wait(2)
    # The thread is inside proxy.shutdown, so the provider's shutdown must not run yet.
    assert not shutdown_started.wait(0.5)

    release_flush.set()
    flush_thread.join(5)
    shutdown_thread.join(5)
    assert shutdown_started.is_set()
