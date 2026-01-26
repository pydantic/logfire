import pytest
from _typeshed import Incomplete
from collections.abc import Generator
from logfire import Logfire as Logfire, LogfireSpan as LogfireSpan
from typing import Any

class LogfirePluginConfig:
    """Configuration for the Logfire pytest plugin."""
    logfire_instance: Incomplete
    service_name: Incomplete
    trace_phases: Incomplete
    def __init__(self, logfire_instance: Logfire, service_name: str, trace_phases: bool) -> None: ...

def pytest_addoption(parser: pytest.Parser) -> None:
    """Add Logfire options to pytest."""
def pytest_configure(config: pytest.Config) -> None:
    """Configure Logfire when the plugin is enabled."""
def pytest_sessionstart(session: pytest.Session) -> None:
    """Create a session span when the test session starts."""
def pytest_runtest_protocol(item: pytest.Item, nextitem: pytest.Item | None) -> Generator[None]:
    """Create a span for each test."""
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo[Any]) -> Generator[None, pytest.TestReport, None]:
    """Record test outcomes and exceptions."""
def pytest_runtest_setup(item: pytest.Item) -> Generator[None]:
    """Trace test setup phase if --logfire-trace-phases is enabled."""
def pytest_runtest_call(item: pytest.Item) -> Generator[None]:
    """Trace test call phase if --logfire-trace-phases is enabled."""
def pytest_runtest_teardown(item: pytest.Item) -> Generator[None]:
    """Trace test teardown phase if --logfire-trace-phases is enabled."""
def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    """End the session span and flush traces."""
@pytest.fixture
def logfire_pytest(request: pytest.FixtureRequest) -> Logfire:
    """Provide a Logfire instance configured for the pytest plugin.

    This fixture provides a Logfire instance that sends spans to Logfire when the
    pytest plugin is enabled (via `--logfire` flag). Use this instead of the global
    `logfire` module when you want spans created in tests to be sent to Logfire
    as part of your test traces.

    When the plugin is not enabled, this fixture returns a local-only instance
    that doesn't send data anywhere.
    """
