"""Isolated POSIX fork probe, invoked by test_variables with a hard timeout."""
# pyright: reportPrivateUsage=false

import os
import signal
import sys
import threading
import traceback
import warnings
from contextlib import ExitStack

from logfire._internal.config import VariablesOptions
from logfire.variables.config import VariablesConfig
from logfire.variables.remote import LogfireRemoteVariableProvider


def main() -> None:
    """Fork while another thread owns every provider lock, including the Once guard."""
    # Registered first so even a deadlock inside a later child hook is bounded.
    os.register_at_fork(after_in_child=lambda: signal.alarm(5))
    provider = LogfireRemoteVariableProvider(
        base_url='http://127.0.0.1:1', token='unused', options=VariablesOptions(block_before_first_resolve=False)
    )
    provider._config = VariablesConfig(variables={})
    provider._evaluation_state = 'ready'
    stopped = '--stopped' in sys.argv
    if stopped:
        provider.shutdown()
    inherited_session, inherited_config = provider._session, provider._config
    locks = [
        provider._refresh_lock,
        provider._session_lock,
        provider._lifecycle_lock,
        provider._sse_response_lock,
        provider._reset_once._lock,
    ]
    acquired, release = threading.Event(), threading.Event()

    def hold_locks() -> None:
        with ExitStack() as stack:
            for lock in locks:
                stack.enter_context(lock)
            acquired.set()
            release.wait(10)

    thread = threading.Thread(target=hold_locks, daemon=True)
    thread.start()
    assert acquired.wait(2)
    try:
        # Forking with held locks is the behavior under test, not a production pattern.
        with warnings.catch_warnings():
            warnings.filterwarnings('ignore', message='.*multi-threaded.*', category=DeprecationWarning)
            child = os.fork()
        if child == 0:
            try:
                assert provider._pid == os.getpid()
                assert provider._shutdown == stopped
                assert provider._config is inherited_config
                assert (provider._session is inherited_session) == stopped
                for lock in (
                    provider._refresh_lock,
                    provider._session_lock,
                    provider._lifecycle_lock,
                    provider._sse_response_lock,
                    provider._reset_once._lock,
                ):
                    assert lock.acquire(timeout=0.5)
                    lock.release()
                assert provider.get_evaluation_state() == ('not_ready' if stopped else 'ready')
                provider.shutdown(timeout_millis=50)
            except BaseException:
                os.write(2, traceback.format_exc().encode())
                os._exit(1)
            os._exit(0)
        _, status = os.waitpid(child, 0)
        assert os.waitstatus_to_exitcode(status) == 0, status
    finally:
        release.set()
        thread.join(2)
        provider.shutdown()


if __name__ == '__main__':
    main()
