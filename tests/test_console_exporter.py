from __future__ import annotations

import io

import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import ReadableSpan

from logfire.exporters.console import (
    IndentedConsoleSpanExporter,
    ShowParentsConsoleSpanExporter,
    SimpleConsoleSpanExporter,
)

tracer = trace.get_tracer('test')


NANOSECONDS_PER_SECOND = int(1e9)


@pytest.fixture
def simple_spans() -> list[ReadableSpan]:
    trace_id = 0
    root_span_id = 1
    pending_span_id = 2
    log_span_id = 3
    return [
        ReadableSpan(
            name='rootSpan',
            context=trace.SpanContext(trace_id=trace_id, span_id=pending_span_id, is_remote=False),
            parent=trace.SpanContext(trace_id=trace_id, span_id=root_span_id, is_remote=False),
            attributes={
                'logfire.span_type': 'pending_span',
                'logfire.msg_template': 'rootSpan',
                'logfire.msg': 'rootSpan',
            },
            start_time=1 * NANOSECONDS_PER_SECOND,
            end_time=1 * NANOSECONDS_PER_SECOND,
        ),
        ReadableSpan(
            name='childSpan {a=}',
            context=trace.SpanContext(trace_id=trace_id, span_id=log_span_id, is_remote=False),
            parent=trace.SpanContext(trace_id=trace_id, span_id=root_span_id, is_remote=False),
            attributes={
                'logfire.span_type': 'pending_span',
                'logfire.msg_template': 'childSpan {a=}',
                'logfire.msg': 'childSpan 1',
                'a': 1,
                'code.filepath': 'testing.py',
                'code.lineno': 42,
            },
            start_time=2 * NANOSECONDS_PER_SECOND,
            end_time=2 * NANOSECONDS_PER_SECOND,
        ),
        ReadableSpan(
            name='rootSpan',
            context=trace.SpanContext(trace_id=trace_id, span_id=root_span_id, is_remote=False),
            attributes={
                'logfire.span_type': 'span',
                'logfire.msg_template': 'rootSpan',
                'logfire.msg': 'rootSpan',
                'a': 1,
            },
            start_time=1 * NANOSECONDS_PER_SECOND,
            end_time=3 * NANOSECONDS_PER_SECOND,
        ),
    ]


def test_simple_console_exporter_no_colors_concise(simple_spans) -> None:
    out = io.StringIO()
    SimpleConsoleSpanExporter(output=out, verbose=False, colors='never').export(simple_spans)

    # insert_assert(out.getvalue().splitlines())
    assert out.getvalue().splitlines() == [
        '00:00:01.000 rootSpan',
        '00:00:02.000 childSpan 1',
    ]


def test_simple_console_exporter_colors_concise(simple_spans) -> None:
    out = io.StringIO()
    SimpleConsoleSpanExporter(output=out, verbose=False, colors='always').export(simple_spans)

    # insert_assert(out.getvalue().splitlines())
    assert out.getvalue().splitlines() == [
        '\x1b[32m00:00:01.000\x1b[0m rootSpan',
        '\x1b[32m00:00:02.000\x1b[0m childSpan 1',
    ]


def test_simple_console_exporter_no_colors_verbose(simple_spans) -> None:
    out = io.StringIO()
    SimpleConsoleSpanExporter(output=out, verbose=True, colors='never').export(simple_spans)

    # insert_assert(out.getvalue().splitlines())
    assert out.getvalue().splitlines() == [
        '00:00:01.000 rootSpan',
        '00:00:02.000 childSpan 1',
        '             │ testing.py:42 ',
    ]


def pending_span(
    msg_template: str, timestamp: int, trace_id: int, span_id: int, parent_id: int, grand_parent_id: int | None = None
) -> ReadableSpan:
    extra_attributes = {}
    if grand_parent_id is not None:
        extra_attributes['logfire.pending_parent_id'] = format(grand_parent_id, '016x')
    return ReadableSpan(
        name=msg_template,
        context=trace.SpanContext(trace_id=trace_id, span_id=span_id, is_remote=False),
        parent=trace.SpanContext(trace_id=trace_id, span_id=parent_id, is_remote=False),
        attributes={
            'logfire.span_type': 'pending_span',
            'logfire.msg_template': msg_template,
            'logfire.msg': msg_template,
            **extra_attributes,
        },
        start_time=timestamp * NANOSECONDS_PER_SECOND,
        end_time=timestamp * NANOSECONDS_PER_SECOND,
    )


def log_span(
    msg_template: str, timestamp: int, trace_id: int, span_id: int, parent_id: int | None = None
) -> ReadableSpan:
    if parent_id is not None:
        parent = trace.SpanContext(trace_id=trace_id, span_id=parent_id, is_remote=False)
    else:
        parent = None
    return ReadableSpan(
        name=msg_template,
        context=trace.SpanContext(trace_id=trace_id, span_id=span_id, is_remote=False),
        parent=parent,
        attributes={
            'logfire.span_type': 'log',
            'logfire.msg_template': msg_template,
            'logfire.msg': msg_template,
        },
        start_time=timestamp * NANOSECONDS_PER_SECOND,
        end_time=timestamp * NANOSECONDS_PER_SECOND,
    )


def span_span(
    msg_template: str,
    start_timestamp: int,
    end_timestamp: int,
    trace_id: int,
    span_id: int,
    parent_id: int | None = None,
) -> ReadableSpan:
    if parent_id is not None:
        parent = trace.SpanContext(trace_id=trace_id, span_id=parent_id, is_remote=False)
    else:
        parent = None
    return ReadableSpan(
        name=msg_template,
        context=trace.SpanContext(trace_id=trace_id, span_id=span_id, is_remote=False),
        parent=parent,
        attributes={
            'logfire.span_type': 'span',
            'logfire.msg_template': msg_template,
            'logfire.msg': msg_template,
        },
        start_time=start_timestamp * NANOSECONDS_PER_SECOND,
        end_time=end_timestamp * NANOSECONDS_PER_SECOND,
    )


def test_indented_console_exporter() -> None:
    trace_id = 0
    root_span_id = 1
    pending_span_id = 2
    log_span_id = 3

    out = io.StringIO()
    exporter = IndentedConsoleSpanExporter(output=out, verbose=False, colors='never')
    assert exporter._indent_level == {}
    exporter.export([pending_span('rootSpan', 1, trace_id, pending_span_id, root_span_id)])
    assert exporter._indent_level == {1: 1}
    exporter.export(
        [
            log_span('logSpan', 2, trace_id, log_span_id, root_span_id),
            span_span('rootSpan', 1, 3, trace_id, root_span_id),
        ]
    )
    assert exporter._indent_level == {}

    # insert_assert(out.getvalue().splitlines())
    assert out.getvalue().splitlines() == [
        '00:00:01.000 rootSpan',
        '00:00:02.000   logSpan',
    ]


def test_indented_console_exporter_nested() -> None:
    trace_id = 0
    root_span_id = 1
    root_pending_span_id = 2
    nested_span_id = 3
    nested_pending_span_id = 4
    log_1_span_id = 5
    log_2_span_id = 6
    spans = [
        pending_span('rootSpan', 1, trace_id, root_pending_span_id, root_span_id),
        pending_span('nestedSpan', 2, trace_id, nested_pending_span_id, nested_span_id, root_span_id),
        log_span('logSpan 1', 3, trace_id, log_1_span_id, nested_span_id),
        span_span('nestedSpan', 2, 4, trace_id, nested_span_id, root_span_id),
        log_span('logSpan 2', 5, trace_id, log_2_span_id, root_span_id),
        span_span('rootSpan', 1, 5, trace_id, root_span_id),
    ]

    out = io.StringIO()
    exporter = IndentedConsoleSpanExporter(output=out, verbose=False, colors='never')
    assert exporter._indent_level == {}
    exporter.export(spans)
    assert exporter._indent_level == {}

    # insert_assert(out.getvalue().splitlines())
    assert out.getvalue().splitlines() == [
        '00:00:01.000 rootSpan',
        '00:00:02.000   nestedSpan',
        '00:00:03.000     logSpan 1',
        '00:00:05.000   logSpan 2',
    ]


def test_show_parents_console_exporter() -> None:
    trace_id = 0
    root_span_id = 1
    pending_span_id = 2
    log_span_id = 3

    out = io.StringIO()
    exporter = ShowParentsConsoleSpanExporter(output=out, verbose=False, colors='never')
    assert exporter._span_history == {}
    assert exporter._span_stack == []
    exporter.export([pending_span('rootSpan', 1, trace_id, pending_span_id, root_span_id)])
    assert exporter._span_history == {1: (0, 'rootSpan', 0)}
    assert exporter._span_stack == [1]
    exporter.export(
        [
            log_span('logSpan', 2, trace_id, log_span_id, root_span_id),
            span_span('rootSpan', 1, 3, trace_id, root_span_id),
        ]
    )
    assert exporter._span_history == {}
    assert exporter._span_stack == []

    # insert_assert(out.getvalue().splitlines())
    assert out.getvalue().splitlines() == [
        '00:00:01.000 rootSpan',
        '00:00:02.000   logSpan',
    ]


def test_show_parents_console_exporter_nested() -> None:
    trace_id = 0
    root_span_id = 1
    root_pending_span_id = 2
    nested_span_id = 3
    nested_pending_span_id = 4
    log_1_span_id = 5
    log_2_span_id = 6

    out = io.StringIO()
    exporter = ShowParentsConsoleSpanExporter(output=out, verbose=False, colors='never')

    exporter.export(
        [
            pending_span('rootSpan', 1, trace_id, root_pending_span_id, root_span_id),
            pending_span('nestedSpan', 2, trace_id, nested_pending_span_id, nested_span_id, root_span_id),
            log_span('logSpan 1', 3, trace_id, log_1_span_id, nested_span_id),
        ]
    )

    # insert_assert(exporter._span_history)
    assert exporter._span_history == {1: (0, 'rootSpan', 0), 3: (1, 'nestedSpan', 1)}
    # insert_assert(exporter._span_stack)
    assert exporter._span_stack == [1, 3]

    exporter.export(
        [
            span_span('nestedSpan', 2, 4, trace_id, nested_span_id, root_span_id),
        ]
    )

    # insert_assert(exporter._span_history)
    assert exporter._span_history == {1: (0, 'rootSpan', 0)}
    # insert_assert(exporter._span_stack)
    assert exporter._span_stack == [1]

    exporter.export(
        [
            log_span('logSpan 2', 5, trace_id, log_2_span_id, root_span_id),
            span_span('rootSpan', 1, 5, trace_id, root_span_id),
        ]
    )
    assert exporter._span_history == {}
    assert exporter._span_stack == []

    # insert_assert(out.getvalue().splitlines())
    assert out.getvalue().splitlines() == [
        '00:00:01.000 rootSpan',
        '00:00:02.000   nestedSpan',
        '00:00:03.000     logSpan 1',
        '00:00:05.000   logSpan 2',
    ]


def test_show_parents_console_exporter_interleaved() -> None:
    a_trace_id = 0
    a_span_id = 1
    a_pending_span_id = 2
    a_log_id = 3
    b_trace_id = 4
    b_span_id = 5
    b_pending_span_id = 6
    b_log_id = 7

    out = io.StringIO()
    exporter = ShowParentsConsoleSpanExporter(output=out, verbose=False, colors='never')

    exporter.export(
        [
            pending_span('span a', 1, a_trace_id, a_pending_span_id, a_span_id),
            pending_span('span b', 2, b_trace_id, b_pending_span_id, b_span_id),
            log_span('log a', 3, a_trace_id, a_log_id, a_span_id),
            log_span('log b', 4, b_trace_id, b_log_id, b_span_id),
            span_span('span a', 1, 5, a_trace_id, a_span_id),
            span_span('span b', 1, 6, b_trace_id, b_span_id),
        ]
    )

    assert exporter._span_history == {}
    assert exporter._span_stack == []

    # insert_assert(out.getvalue().splitlines())
    assert out.getvalue().splitlines() == [
        '00:00:01.000 span a',
        '00:00:02.000 span b',
        '             span a',
        '00:00:03.000   log a',
        '             span b',
        '00:00:04.000   log b',
    ]
