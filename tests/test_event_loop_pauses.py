import asyncio
import json
import threading
import time

import pytest
from dirty_equals import IsFloat, IsInt, IsStr
from inline_snapshot import snapshot

import logfire
from logfire.testing import TestExporter


def watchdog_threads() -> set[threading.Thread]:
    return {t for t in threading.enumerate() if t.name == 'logfire-event-loop-watchdog'}


@pytest.mark.anyio
async def test_log_event_loop_pauses(exporter: TestExporter) -> None:
    with logfire.log_event_loop_pauses(slow_duration=0.1, check_interval=0.01):
        await asyncio.sleep(0.02)  # let the heartbeat get going
        time.sleep(0.4)  # block the event loop
        # The warning is logged from the watchdog thread shortly after the loop recovers.
        for _ in range(500):
            if exporter.exported_spans:
                break
            await asyncio.sleep(0.01)

    assert exporter.exported_spans[0].instrumentation_scope.name == 'logfire.asyncio'  # type: ignore

    [span] = exporter.exported_spans_as_dict()
    # The loop thread was blocked in `time.sleep` above when the stack was sampled,
    # so the innermost frame of the sampled stack is this test function.
    stack = json.loads(span['attributes'].pop('stack'))
    assert stack[-1]['code.function'] == 'test_log_event_loop_pauses'
    assert span == snapshot(
        {
            'name': 'Event loop blocked for {duration:.3f} seconds',
            'context': {'trace_id': IsInt, 'span_id': IsInt, 'is_remote': False},
            'parent': None,
            'start_time': IsInt,
            'end_time': IsInt,
            'attributes': {
                'logfire.span_type': 'log',
                'logfire.level_num': 13,
                'logfire.msg_template': 'Event loop blocked for {duration:.3f} seconds',
                'logfire.msg': IsStr(regex=r'Event loop blocked for 0\.\d{3} seconds'),
                'code.filepath': 'test_event_loop_pauses.py',
                'code.function': 'test_log_event_loop_pauses',
                'code.lineno': 123,
                'duration': IsFloat(gt=0.3, lt=10),
                'logfire.json_schema': '{"type":"object","properties":{"duration":{},"stack":{"type":"array"}}}',
            },
        }
    )


@pytest.mark.anyio
async def test_no_warning_for_responsive_loop(exporter: TestExporter) -> None:
    with logfire.log_event_loop_pauses(slow_duration=1, check_interval=0.01):
        for _ in range(10):
            await asyncio.sleep(0.001)
            time.sleep(0.005)  # brief blocking, well under the threshold
    assert not exporter.exported_spans


@pytest.mark.anyio
async def test_context_manager_stops_watchdog(exporter: TestExporter) -> None:
    threads_before = watchdog_threads()
    with logfire.log_event_loop_pauses():
        [thread] = watchdog_threads() - threads_before
        assert thread.is_alive()
    thread.join(timeout=5)
    assert not thread.is_alive()
    # Let the last scheduled heartbeat fire and see that it doesn't reschedule itself.
    await asyncio.sleep(0.1)
    assert not exporter.exported_spans


@pytest.mark.anyio
async def test_stop_while_loop_blocked(exporter: TestExporter) -> None:
    context = logfire.log_event_loop_pauses(slow_duration=0.05, check_interval=0.01)
    context.__enter__()
    # Stop the watchdog from another thread while the event loop is still blocked.
    timer = threading.Timer(0.2, context.__exit__, (None, None, None))
    timer.start()
    await asyncio.sleep(0.02)
    time.sleep(0.6)  # block the event loop for well over the timer above
    timer.join()
    await asyncio.sleep(0.1)
    # The pause was still in progress when the watchdog was stopped,
    # so its duration is unknown and nothing is logged.
    assert not exporter.exported_spans


def test_watchdog_exits_when_loop_closes(exporter: TestExporter) -> None:
    threads_before = watchdog_threads()

    async def main():
        logfire.log_event_loop_pauses(slow_duration=0.1, check_interval=0.01)

    asyncio.run(main())
    [thread] = watchdog_threads() - threads_before
    thread.join(timeout=5)
    assert not thread.is_alive()
    assert not exporter.exported_spans


def test_requires_running_loop() -> None:
    with pytest.raises(RuntimeError):
        logfire.log_event_loop_pauses()


def test_log_event_loop_pauses_uvloop(exporter: TestExporter) -> None:
    # `log_slow_async_callbacks` can't detect anything under uvloop, whose callback handles
    # are implemented in Cython and never call the patched `asyncio.events.Handle._run`.
    # The heartbeat watchdog doesn't care about the event loop implementation.
    uvloop = pytest.importorskip('uvloop')

    async def main():
        with logfire.log_event_loop_pauses(slow_duration=0.1, check_interval=0.01):
            await asyncio.sleep(0.02)
            time.sleep(0.4)  # block the event loop
            for _ in range(500):
                if exporter.exported_spans:
                    break
                await asyncio.sleep(0.01)

    uvloop.run(main())

    [span] = exporter.exported_spans_as_dict()
    assert span['name'] == 'Event loop blocked for {duration:.3f} seconds'
    assert span['attributes']['code.function'] == 'main'
    duration = span['attributes']['duration']
    assert isinstance(duration, float)
    assert 0.3 < duration < 10
