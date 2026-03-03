from __future__ import annotations

from asyncio.events import Handle

import logfire
from logfire.testing import TestExporter


def test_instrument_asyncio(exporter: TestExporter) -> None:
    """Test that instrument_asyncio patches Handle._run and can be reverted."""
    from opentelemetry.instrumentation.asyncio import AsyncioInstrumentor

    assert Handle._run.__qualname__ == 'Handle._run'

    try:
        with logfire.instrument_asyncio(slow_duration=100):
            # Check that the slow callback patching is in effect
            assert Handle._run.__qualname__ == 'log_slow_callbacks.<locals>.patched_run'

        # Check that the patching is reverted after exiting the context manager
        assert Handle._run.__qualname__ == 'Handle._run'
    finally:
        # Clean up OTel instrumentation (context manager only reverts slow callback patch)
        AsyncioInstrumentor().uninstrument()
