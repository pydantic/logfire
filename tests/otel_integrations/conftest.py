from __future__ import annotations

from collections.abc import Iterator

import pytest
from testcontainers.redis import RedisContainer


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        '--record-claude-cassettes',
        action='store_true',
        default=False,
        help='Record cassettes using a real claude CLI instead of replaying.',
    )


@pytest.fixture(scope='module')
def redis_container() -> Iterator[RedisContainer]:
    with RedisContainer('redis:latest') as redis:
        yield redis
