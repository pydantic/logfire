from __future__ import annotations

import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        '--record-cassettes',
        action='store_true',
        default=False,
        help='Record cassettes using a real claude CLI instead of replaying.',
    )


def pytest_configure(config: pytest.Config) -> None:
    # The Claude Agent SDK's SubprocessCLITransport doesn't close its internal
    # anyio MemoryObjectStreams. When GC collects them during a later test's
    # setup/teardown, it triggers PytestUnraisableExceptionWarning. Suppress
    # these globally for the otel_integrations directory since per-file
    # pytestmark filterwarnings doesn't cover cross-module GC timing.
    config.addinivalue_line(
        'filterwarnings',
        'ignore::pytest.PytestUnraisableExceptionWarning',
    )
