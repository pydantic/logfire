from __future__ import annotations

import io

import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import ReadableSpan

from logfire.exporters.console import ConsoleColorsValues, ConsoleSpanExporter

tracer = trace.get_tracer('test')


NANOSECONDS_PER_SECOND = int(1e9)


def test_console_exporter() -> None:
    out = io.StringIO()

    spans = [
        ReadableSpan(
            name='rootSpan',
            context=trace.SpanContext(trace_id=0, span_id=1, is_remote=False),
            parent=trace.SpanContext(trace_id=0, span_id=2, is_remote=False),
            attributes={'logfire.span_type': 'pending_span', 'logfire.msg_template': 'rootSpan'},
            start_time=2 * NANOSECONDS_PER_SECOND,
            end_time=2 * NANOSECONDS_PER_SECOND,
        ),
        ReadableSpan(
            name='childSpan {a=}',
            context=trace.SpanContext(trace_id=0, span_id=3, is_remote=False),
            parent=trace.SpanContext(trace_id=0, span_id=4, is_remote=False),
            attributes={
                'logfire.span_type': 'pending_span',
                'logfire.pending_parent_id': '0000000000000000',
                'logfire.msg_template': 'childSpan',
                'logfire.msg': 'childSpan 1',
                'a': 1,
            },
            start_time=5 * NANOSECONDS_PER_SECOND,
            end_time=5 * NANOSECONDS_PER_SECOND,
        ),
        ReadableSpan(
            name='childSpan',
            context=trace.SpanContext(trace_id=0, span_id=4, is_remote=False),
            parent=trace.SpanContext(trace_id=0, span_id=2, is_remote=False),
            attributes={
                'logfire.span_type': 'span',
                'logfire.pending_parent_id': '0000000000000000',
                'logfire.msg_template': 'childSpan',
                'logfire.msg': 'childSpan 1',
                'a': 1,
            },
            start_time=5 * NANOSECONDS_PER_SECOND,
            end_time=6 * NANOSECONDS_PER_SECOND,
        ),
        ReadableSpan(
            name='rootSpan',
            context=trace.SpanContext(trace_id=0, span_id=2, is_remote=False),
            parent=None,
            attributes={'logfire.span_type': 'span', 'logfire.msg_template': 'rootSpan'},
            start_time=2 * NANOSECONDS_PER_SECOND,
            end_time=7 * NANOSECONDS_PER_SECOND,
        ),
    ]

    ConsoleSpanExporter(output=out, verbose=True, colors='always').export(spans)

    # insert_assert(out.getvalue().splitlines())
    assert out.getvalue().splitlines() == [
        '\x1b[2m1970-01-01 00:00:02\x1b[0m \x1b[1mrootSpan                      \x1b[0m \x1b[36mspan_id\x1b[0m=\x1b[35m0000000000000002\x1b[0m \x1b[36mspan_type\x1b[0m=\x1b[35mspan\x1b[0m',
        '  \x1b[2m1970-01-01 00:00:05\x1b[0m \x1b[1mchildSpan 1                   \x1b[0m \x1b[36mspan_id\x1b[0m=\x1b[35m0000000000000004\x1b[0m \x1b[36mspan_type\x1b[0m=\x1b[35mspan\x1b[0m \x1b[36mparent_id\x1b[0m=\x1b[35m0000000000000002\x1b[0m',
    ]

    out = io.StringIO()

    ConsoleSpanExporter(output=out, verbose=False, colors='always').export(spans)

    # insert_assert(out.getvalue().splitlines())
    assert out.getvalue().splitlines() == [
        '\x1b[2m1970-01-01 00:00:02\x1b[0m \x1b[1mrootSpan\x1b[0m',
        '  \x1b[2m1970-01-01 00:00:05\x1b[0m \x1b[1mchildSpan 1\x1b[0m',
    ]


colored_spans = [
    '\x1b[2m1970-01-01 00:00:02\x1b[0m \x1b[1mrootSpan                      \x1b[0m \x1b[36mspan_id\x1b[0m=\x1b[35m0000000000000002\x1b[0m \x1b[36mspan_type\x1b[0m=\x1b[35mspan\x1b[0m'
]
uncolored_spans = ['1970-01-01 00:00:02 rootSpan                       span_id=0000000000000002 span_type=span']
uncolored_without_timestamp_spans = ['rootSpan                       span_id=0000000000000002 span_type=span']


@pytest.mark.parametrize(
    'colors,indent_spans,include_timestamp,verbose,expected',
    [
        (
            'always',
            True,
            True,
            True,
            [
                '\x1b[2m1970-01-01 00:00:02\x1b[0m \x1b[1mrootSpan                      \x1b[0m \x1b[36mspan_id\x1b[0m=\x1b[35m0000000000000002\x1b[0m \x1b[36mspan_type\x1b[0m=\x1b[35mspan\x1b[0m',
                '  \x1b[2m1970-01-01 00:00:05\x1b[0m \x1b[1mchildSpan 1                   \x1b[0m \x1b[36mspan_id\x1b[0m=\x1b[35m0000000000000004\x1b[0m \x1b[36mspan_type\x1b[0m=\x1b[35mspan\x1b[0m \x1b[36mparent_id\x1b[0m=\x1b[35m0000000000000002\x1b[0m',
            ],
        ),
        (
            'always',
            True,
            True,
            False,
            [
                '\x1b[2m1970-01-01 00:00:02\x1b[0m \x1b[1mrootSpan\x1b[0m',
                '  \x1b[2m1970-01-01 00:00:05\x1b[0m \x1b[1mchildSpan 1\x1b[0m',
            ],
        ),
        (
            'never',
            True,
            True,
            False,
            ['1970-01-01 00:00:02 rootSpan', '  1970-01-01 00:00:05 childSpan 1'],
        ),
        (
            'never',
            False,
            True,
            False,
            ['1970-01-01 00:00:02 rootSpan', '1970-01-01 00:00:05 childSpan 1'],
        ),
        (
            'never',
            False,
            False,
            False,
            ['rootSpan', 'childSpan 1'],
        ),
    ],
)
def test_console_exporter_options(
    colors: ConsoleColorsValues,
    indent_spans: bool,
    include_timestamp: bool,
    verbose: bool,
    expected: list[str],
) -> None:
    out = io.StringIO()

    spans = [
        ReadableSpan(
            name='childSpan',
            context=trace.SpanContext(trace_id=0, span_id=4, is_remote=False),
            parent=trace.SpanContext(trace_id=0, span_id=2, is_remote=False),
            attributes={
                'logfire.span_type': 'span',
                'logfire.pending_parent_id': '0000000000000000',
                'logfire.msg_template': 'childSpan',
                'logfire.msg': 'childSpan 1',
                'a': 1,
            },
            start_time=5 * NANOSECONDS_PER_SECOND,
            end_time=6 * NANOSECONDS_PER_SECOND,
        ),
        ReadableSpan(
            name='rootSpan',
            context=trace.SpanContext(trace_id=0, span_id=2, is_remote=False),
            parent=None,
            attributes={'logfire.span_type': 'span', 'logfire.msg_template': 'rootSpan'},
            start_time=2 * NANOSECONDS_PER_SECOND,
            end_time=7 * NANOSECONDS_PER_SECOND,
        ),
    ]

    ConsoleSpanExporter(
        output=out, colors=colors, indent_spans=indent_spans, include_timestamp=include_timestamp, verbose=verbose
    ).export(spans)

    # insert_assert(out.getvalue().splitlines())
    assert out.getvalue().splitlines() == expected


def test_console_exporter_verbose_tags() -> None:
    out = io.StringIO()

    spans = [
        ReadableSpan(
            name='rootSpan',
            context=trace.SpanContext(trace_id=0, span_id=2, is_remote=False),
            parent=None,
            attributes={
                'logfire.span_type': 'span',
                'logfire.msg_template': 'rootSpan',
                'logfire.tags': ('tag1', 'tag2'),
            },
            start_time=2 * NANOSECONDS_PER_SECOND,
            end_time=7 * NANOSECONDS_PER_SECOND,
        ),
    ]

    ConsoleSpanExporter(output=out, verbose=True).export(spans)

    # insert_assert(out.getvalue().splitlines())
    assert out.getvalue().splitlines() == [
        "1970-01-01 00:00:02 rootSpan                       span_id=0000000000000002 span_type=span tags=('tag1', 'tag2')"
    ]
