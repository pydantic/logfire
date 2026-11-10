from __future__ import annotations

from collections.abc import Iterator

import pytest

from ..utils import isolated_litellm_event_loop_context


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        '--record-claude-cassettes',
        action='store_true',
        default=False,
        help='Record cassettes using a real claude CLI instead of replaying.',
    )


@pytest.fixture
def isolated_litellm_event_loop() -> Iterator[None]:
    with isolated_litellm_event_loop_context():
        yield
