from __future__ import annotations

import asyncio
import asyncio.events
import asyncio.tasks
import inspect
import sys
import threading
import time
from contextlib import AbstractContextManager, contextmanager
from pathlib import Path
from types import CoroutineType
from typing import TYPE_CHECKING, Any

from .constants import ONE_SECOND_IN_NANOSECONDS
from .stack_info import StackInfo, get_code_object_info, get_stack_info_from_frame
from .utils import safe_repr

if TYPE_CHECKING:
    from .main import Logfire

ASYNCIO_PATH = str(Path(asyncio.__file__).parent.absolute())


def log_slow_callbacks(logfire: Logfire, slow_duration: float) -> AbstractContextManager[None]:
    """Log a warning whenever a function running in the asyncio event loop blocks for too long.

    See Logfire.log_slow_async_callbacks.
    Inspired by https://gitlab.com/quantlane/libs/aiodebug.
    """
    original_run = asyncio.events.Handle._run
    logfire = logfire.with_settings(custom_scope_suffix='asyncio')
    timer = logfire.config.advanced.ns_timestamp_generator
    slow_duration *= ONE_SECOND_IN_NANOSECONDS

    def patched_run(self: asyncio.events.Handle) -> Any:
        start_time = timer()
        # Handle._run currently doesn't actually return anything, but maybe it will in the future?
        return_value = original_run(self)
        duration = timer() - start_time
        if duration >= slow_duration:
            try:
                duration /= ONE_SECOND_IN_NANOSECONDS
                callback: Any = self._callback
                logfire.warn(
                    'Async {name} blocked for {duration:.3f} seconds',
                    duration=duration,
                    **_callback_attributes(callback),
                )
            except Exception:  # pragma: no cover
                # Don't crash the event loop for this.
                try:
                    logfire.exception('Error in log_slow_callbacks')
                except Exception:
                    pass
        return return_value

    asyncio.events.Handle._run = patched_run

    @contextmanager
    def patch_context():
        # The user isn't required (or even expected) to use this context manager,
        # which is why the patching has already happened before this point.
        # It exists mostly for tests, and just in case users want it.
        try:
            yield
        finally:
            asyncio.events.Handle._run = original_run

    return patch_context()


class _CallbackAttributes(StackInfo, total=False):
    name: str
    stack: list[StackInfo]


def stack_info_from_coroutine(coro: CoroutineType[Any, Any, Any]) -> StackInfo:
    if frame := coro.cr_frame:
        return get_stack_info_from_frame(frame)
    else:
        # This typically means that the coroutine has finished.
        # We can't get an exact line number, so we'll use the line number of the code object.
        return get_code_object_info(coro.cr_code)


def _callback_attributes(callback: Any) -> _CallbackAttributes:
    task = getattr(callback, '__self__', None)
    if isinstance(task, asyncio.tasks.Task):
        # `callback` is a bound method of a Task.
        # This is the common case for typical user code.
        # In particular this method is usually for advancing an async function (coroutine) to the next `await`.
        coro: Any = task.get_coro()  # pyright: ignore[reportUnknownVariableType]
        result: _CallbackAttributes = {'name': f'task {task.get_name()}'}
        if not isinstance(coro, CoroutineType):  # pragma: no cover
            return result
        stack_info = stack_info_from_coroutine(coro)  # pyright: ignore[reportUnknownArgumentType]
        result = {**result, **stack_info}
        if function_name := stack_info.get('code.function'):  # pragma: no branch
            result['name'] += f' ({function_name})'

        # Walk through the coroutines being awaited to create an 'async stacktrace'
        stack = [stack_info]
        while isinstance(coro := coro.cr_await, CoroutineType):
            stack_info = stack_info_from_coroutine(coro)  # pyright: ignore[reportUnknownArgumentType]
            # Ignore frames from the stdlib asyncio
            if not stack_info.get('code.filepath', '').startswith(ASYNCIO_PATH):
                stack.append(stack_info)
        result['stack'] = stack

        return result

    # `callback` is a callable passed to a low-level API like `call_soon`.
    # Hopefully it's a function, but maybe not.
    callback = inspect.unwrap(callback)
    result: _CallbackAttributes = {}
    code = getattr(callback, '__code__', None)
    if code:  # pragma: no branch
        result = {**get_code_object_info(code)}
    name: str = (
        getattr(callback, '__qualname__', '') or getattr(callback, '__name__', '') or result.get('code.function', '')
    )
    name = name or safe_repr(callback)
    result['name'] = f'callback {name}'
    return result


def log_event_loop_pauses(
    logfire: Logfire, slow_duration: float, check_interval: float | None
) -> AbstractContextManager[None]:
    """Log a warning whenever the current event loop is unresponsive for too long.

    See Logfire.log_event_loop_pauses.
    """
    loop = asyncio.get_running_loop()
    if check_interval is None:
        check_interval = slow_duration / 4
    logfire = logfire.with_settings(custom_scope_suffix='asyncio')
    watchdog = _EventLoopWatchdog(logfire, loop, slow_duration, check_interval)
    watchdog.start()

    @contextmanager
    def stop_context():
        # The user isn't required to use this context manager,
        # monitoring has already started before this point.
        try:
            yield
        finally:
            watchdog.stop()

    return stop_context()


class _EventLoopWatchdog:
    """Detects event loop pauses with a heartbeat scheduled on the loop and a thread watching it.

    A `call_later` chain on the event loop records the time of each beat.
    A daemon thread checks how overdue the next beat is: if the loop doesn't run the heartbeat
    for `slow_duration` beyond its schedule, the loop is considered blocked, and the thread
    samples the loop thread's stack right away to see what is blocking it.
    Once the loop recovers, a warning is logged with the measured pause duration and that stack.

    Unlike `log_slow_callbacks` this doesn't depend on `asyncio.events.Handle._run`,
    so it works with any event loop implementation, including uvloop.
    """

    def __init__(self, logfire: Logfire, loop: asyncio.AbstractEventLoop, slow_duration: float, check_interval: float):
        self.logfire = logfire
        self.loop = loop
        self.slow_duration = slow_duration
        self.check_interval = check_interval
        # `log_event_loop_pauses` requires a running loop, so the current thread is the loop's thread.
        self.loop_thread_id = threading.get_ident()
        self.last_beat = time.monotonic()
        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=self._watch, name='logfire-event-loop-watchdog', daemon=True)

    def start(self) -> None:
        self._beat()
        self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()

    def _beat(self) -> None:
        # Runs on the event loop: record that the loop is responsive and schedule the next beat.
        self.last_beat = time.monotonic()
        if not self.stop_event.is_set():
            self.loop.call_later(self.check_interval, self._beat)

    def _watch(self) -> None:
        # Runs on the watchdog thread.
        while not self.stop_event.wait(self.check_interval):
            if self.loop.is_closed():
                return
            beat = self.last_beat
            # The next beat was due `check_interval` after the last one; anything beyond that is a pause.
            if time.monotonic() - beat - self.check_interval < self.slow_duration:
                continue
            # The loop is blocked right now. Sample its thread's stack to see what's blocking it,
            # then wait for the loop to recover to measure the total pause.
            stack = self._sample_stack()
            while self.last_beat == beat and not self.loop.is_closed():
                if self.stop_event.wait(self.check_interval):
                    # Stopped while the loop was still blocked; the pause's duration is unknown.
                    return
            if self.last_beat == beat:  # pragma: no cover
                return  # The loop closed while blocked.
            duration = self.last_beat - beat - self.check_interval
            self._log_pause(duration, stack)

    def _sample_stack(self) -> list[StackInfo]:
        frame = sys._current_frames().get(self.loop_thread_id)  # pyright: ignore[reportPrivateUsage]
        stack: list[StackInfo] = []
        while frame is not None:
            stack_info = get_stack_info_from_frame(frame)
            # Ignore frames from the stdlib asyncio
            if not stack_info.get('code.filepath', '').startswith(ASYNCIO_PATH):
                stack.append(stack_info)
            frame = frame.f_back
        # Match the order of the 'stack' in `_callback_attributes`: outermost frame first.
        stack.reverse()
        return stack

    def _log_pause(self, duration: float, stack: list[StackInfo]) -> None:
        try:
            attributes: _CallbackAttributes = {'stack': stack}
            if stack:  # pragma: no branch
                # The innermost frame is where the loop thread was blocked when sampled.
                attributes = {**stack[-1], **attributes}
            self.logfire.warn(
                'Event loop blocked for {duration:.3f} seconds',
                duration=duration,
                **attributes,
            )
        except Exception:  # pragma: no cover
            # Don't crash the watchdog thread for this.
            try:
                self.logfire.exception('Error in log_event_loop_pauses')
            except Exception:
                pass
