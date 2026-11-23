import pytest
from celery import Celery, signals
import logfire

@pytest.fixture(autouse=True)
def reset_logfire():
    # Ensure a clean state for each test
    logfire._reset_global_state_for_tests()
    yield
    logfire._reset_global_state_for_tests()

def test_celery_instrumentation_registers_worker_init_signal():
    # Apply instrumentation
    logfire.instrument_celery()

    # Collect the registered receivers for the worker_init signal
    receivers = [receiver for _, receiver in signals.worker_init.receivers]
    assert any("logfire" in r.__module__ for r in receivers), (
        "Logfire's Celery worker_init handler was not registered"
    )

def test_celery_task_executes_under_instrumentation():
    logfire.instrument_celery()
    app = Celery("test_app")
    # Run tasks eagerly so no broker is required
    app.conf.task_always_eager = True

    @app.task
    def add(x: int, y: int) -> int:
        return x + y

    result = add.delay(1, 2)
    assert result.get(timeout=5) == 3
