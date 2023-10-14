import io

from opentelemetry import trace
from opentelemetry.sdk.trace import ReadableSpan

from logfire.exporters.console import ConsoleSpanExporter

tracer = trace.get_tracer('test')


NANOSECONDS_PER_SECOND = int(1e9)


def test_console_exporter() -> None:
    out = io.StringIO()

    spans = [
        ReadableSpan(
            name='rootSpan',
            context=trace.SpanContext(trace_id=0, span_id=1, is_remote=False),
            parent=trace.SpanContext(trace_id=0, span_id=2, is_remote=False),
            attributes={'logfire.span_type': 'start_span', 'logfire.msg_template': 'rootSpan'},
            start_time=2 * NANOSECONDS_PER_SECOND,
            end_time=2 * NANOSECONDS_PER_SECOND,
        ),
        ReadableSpan(
            name='childSpan',
            context=trace.SpanContext(trace_id=0, span_id=3, is_remote=False),
            parent=trace.SpanContext(trace_id=0, span_id=4, is_remote=False),
            attributes={
                'logfire.span_type': 'start_span',
                'logfire.msg_template': 'childSpan',
                'logfire.start_parent_id': 0,
            },
            start_time=5 * NANOSECONDS_PER_SECOND,
            end_time=5 * NANOSECONDS_PER_SECOND,
        ),
        ReadableSpan(
            name='childSpan',
            context=trace.SpanContext(trace_id=0, span_id=4, is_remote=False),
            parent=trace.SpanContext(trace_id=0, span_id=2, is_remote=False),
            attributes={'logfire.span_type': 'span', 'logfire.start_parent_id': 0},
            start_time=5 * NANOSECONDS_PER_SECOND,
            end_time=6 * NANOSECONDS_PER_SECOND,
        ),
        ReadableSpan(
            name='rootSpan',
            context=trace.SpanContext(trace_id=0, span_id=2, is_remote=False),
            parent=None,
            attributes={'logfire.span_type': 'span'},
            start_time=2 * NANOSECONDS_PER_SECOND,
            end_time=7 * NANOSECONDS_PER_SECOND,
        ),
    ]

    ConsoleSpanExporter(output=out, verbose=True).export(spans)

    print(out.getvalue())

    # insert_assert(out.getvalue().splitlines())
    assert out.getvalue().splitlines() == [
        '\x1b[2m1970-01-01 00:00:02\x1b[0m \x1b[1mrootSpan                      \x1b[0m \x1b[36mspan_id\x1b[0m=\x1b[35m0000000000000002\x1b[0m \x1b[36mspan_type\x1b[0m=\x1b[35mspan\x1b[0m',
        '  \x1b[2m1970-01-01 00:00:05\x1b[0m \x1b[1mchildSpan                     \x1b[0m \x1b[36mspan_id\x1b[0m=\x1b[35m0000000000000004\x1b[0m \x1b[36mspan_type\x1b[0m=\x1b[35mspan\x1b[0m \x1b[36mparent_id\x1b[0m=\x1b[35m0000000000000002\x1b[0m',
    ]

    out = io.StringIO()

    ConsoleSpanExporter(output=out, verbose=False).export(spans)

    # insert_assert(out.getvalue().splitlines())
    assert out.getvalue().splitlines() == [
        '\x1b[2m1970-01-01 00:00:02\x1b[0m \x1b[1mrootSpan\x1b[0m',
        '  \x1b[2m1970-01-01 00:00:05\x1b[0m \x1b[1mchildSpan\x1b[0m',
    ]
