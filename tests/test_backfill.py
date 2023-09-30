import json
from datetime import datetime
from pathlib import Path

import pytest

from logfire.backfill import EndSpan, PrepareBackfill, StartSpan


def test_backfill(tmp_path: Path):
    path = tmp_path / 'test.json'
    with PrepareBackfill(path) as prep_backfill:
        start = StartSpan(
            span_name='session',
            msg_template='session {user_id=} {path=}',
            service_name='docs.pydantic.dev',
            log_attributes={'user_id': '123', 'path': '/test'},
            span_id=1,
            trace_id=2,
            start_timestamp=datetime(2023, 1, 1, 0, 0, 0),
        )
        prep_backfill.write(start)

        end = EndSpan(span_id=1, end_timestamp=datetime(2023, 1, 2, 0, 0, 1))
        prep_backfill.write(end)

        # wrong id - already removed
        end = EndSpan(span_id=1, end_timestamp=datetime(2023, 1, 2, 0, 0, 1))
        with pytest.raises(AssertionError, match='end span ID 1 not found in open spans'):
            prep_backfill.write(end)

    lines = [json.loads(line) for line in path.read_bytes().splitlines() if line]
    # insert_assert(lines)
    assert lines == [
        {
            'type': 'start_span',
            'span_name': 'session',
            'msg_template': 'session {user_id=} {path=}',
            'service_name': 'docs.pydantic.dev',
            'log_attributes': {'user_id': '123', 'path': '/test'},
            'span_id': 1,
            'trace_id': 2,
            'parent_span_id': None,
            'start_timestamp': '2023-01-01T00:00:00',
            'formatted_msg': None,
        },
        {'type': 'end_span', 'span_id': 1, 'end_timestamp': '2023-01-02T00:00:01'},
    ]
