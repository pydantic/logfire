from __future__ import annotations

import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        '--record-claude-cassettes',
        action='store_true',
        default=False,
        help='Record cassettes using a real claude CLI instead of replaying.',
    )
