from __future__ import annotations

from typing import Any, cast

from inline_snapshot import snapshot
from opentelemetry.trace import NonRecordingSpan, get_current_span

import logfire
from logfire._internal.integrations.monty import LogfireMontyTracer
from logfire.testing import TestExporter


def test_logfire_monty_tracer(exporter: TestExporter, config_kwargs: dict[str, Any]) -> None:
    logfire.configure(**config_kwargs, min_level='error')
    scoped = logfire.DEFAULT_LOGFIRE_INSTANCE.with_trace_sample_rate(0.5).with_settings(tags=['monty', 'existing'])
    tracer = LogfireMontyTracer(scoped)

    with logfire.span('parent'):
        rejected = tracer.start_span('too quiet', attributes={'logfire.level_num': 9})
        assert isinstance(rejected, NonRecordingSpan)
        assert rejected.get_span_context() == get_current_span().get_span_context()

        with tracer.start_as_current_span(
            'session {script_name}',
            attributes=cast(Any, {'script_name': 'test.py', 'logfire.level_num': 17, 'logfire.tags': ('existing', 1)}),
        ):
            pass

    spans = exporter.exported_spans_as_dict()
    assert [span['name'] for span in spans] == ['session {script_name}', 'parent']
    assert spans[0]['parent'] == spans[1]['context']
    assert spans[0]['attributes'] == snapshot(
        {
            'script_name': 'test.py',
            'logfire.level_num': 17,
            'logfire.tags': ('existing', 'monty'),
            'logfire.msg_template': 'session {script_name}',
            'logfire.msg': 'session test.py',
            'logfire.sample_rate': 0.5,
            'logfire.span_type': 'span',
        }
    )
