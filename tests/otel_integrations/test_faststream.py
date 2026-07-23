from __future__ import annotations

import pytest
from inline_snapshot import snapshot

from logfire.testing import TestExporter

# FastStream ships its own OpenTelemetry middleware (there's no logfire.instrument_faststream); the
# guide sets it on the broker and relies on logfire.configure() providing the tracer provider. This
# mirrors docs/integrations/event-streams/faststream.md, run against FastStream's in-memory
# TestRedisBroker so no real Redis is needed.
#
# The middleware also emits message IDs and timing metrics, which are non-deterministic, so this
# asserts the span shape (names + the standard messaging attributes) rather than a full snapshot.

pytest.importorskip('faststream')


@pytest.mark.anyio
async def test_faststream(exporter: TestExporter):
    from faststream.redis import RedisBroker, TestRedisBroker
    from faststream.redis.opentelemetry import RedisTelemetryMiddleware

    broker = RedisBroker(middlewares=(RedisTelemetryMiddleware(),))

    # Registered on the broker by the decorators; not called directly.
    @broker.subscriber('test-channel')
    @broker.publisher('another-channel')
    async def handle():  # pyright: ignore[reportUnusedFunction]
        return 'Hi!'

    @broker.subscriber('another-channel')
    async def handle_next(msg: str):  # pyright: ignore[reportUnusedFunction]
        assert msg == 'Hi!'

    async with TestRedisBroker(broker) as br:
        await br.publish('', channel='test-channel')

    spans = exporter.exported_spans_as_dict()

    # A publish and a process span for each channel the message flows through (plus the initial create).
    assert sorted({span['name'] for span in spans}) == snapshot(
        [
            'another-channel process',
            'another-channel publish',
            'test-channel create',
            'test-channel process',
            'test-channel publish',
        ]
    )

    # The spans carry the OpenTelemetry messaging semantic conventions the docs describe.
    process = next(span for span in spans if span['name'] == 'test-channel process')
    assert process['attributes']['messaging.system'] == 'redis'
    assert process['attributes']['messaging.operation'] == 'process'
    assert process['attributes']['messaging.destination_publish.name'] == 'test-channel'
