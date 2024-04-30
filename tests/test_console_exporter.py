# pyright: reportPrivateUsage=false
from __future__ import annotations

import io

import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import ReadableSpan

import logfire
from logfire import ConsoleOptions
from logfire._internal.exporters.console import (
    IndentedConsoleSpanExporter,
    ShowParentsConsoleSpanExporter,
    SimpleConsoleSpanExporter,
)
from logfire.testing import TestExporter
from tests.utils import ReadableSpanModel, SpanContextModel, exported_spans_as_models

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


def test_simple_console_exporter_no_colors_concise(simple_spans: list[ReadableSpan]) -> None:
    out = io.StringIO()
    SimpleConsoleSpanExporter(output=out, verbose=False, colors='never').export(simple_spans)

    # insert_assert(out.getvalue().splitlines())
    assert out.getvalue().splitlines() == [
        '00:00:01.000 rootSpan',
        '00:00:02.000 childSpan 1',
    ]


def test_simple_console_exporter_colors_concise(simple_spans: list[ReadableSpan]) -> None:
    out = io.StringIO()
    SimpleConsoleSpanExporter(output=out, verbose=False, colors='always').export(simple_spans)

    # insert_assert(out.getvalue().splitlines())
    assert out.getvalue().splitlines() == [
        '\x1b[32m00:00:01.000\x1b[0m rootSpan',
        '\x1b[32m00:00:02.000\x1b[0m childSpan 1',
    ]


def test_simple_console_exporter_no_colors_verbose(simple_spans: list[ReadableSpan]) -> None:
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
    extra_attributes: dict[str, str] = {}
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
    if parent_id is not None:  # pragma: no branch
        parent = trace.SpanContext(trace_id=trace_id, span_id=parent_id, is_remote=False)
    else:  # pragma: no cover
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


def test_verbose_attributes(exporter: TestExporter) -> None:
    d = {'a': 1, 'b': 2}
    logfire.info('Hello {name}!', name='world', d=d)
    spans = exported_spans_as_models(exporter)
    # insert_assert(spans)
    assert spans == [
        ReadableSpanModel(
            name='Hello {name}!',
            context=SpanContextModel(trace_id=1, span_id=1, is_remote=False),
            parent=None,
            start_time=1000000000,
            end_time=1000000000,
            attributes={
                'logfire.span_type': 'log',
                'logfire.level_num': 9,
                'logfire.msg_template': 'Hello {name}!',
                'logfire.msg': 'Hello world!',
                'code.lineno': 123,
                'code.filepath': 'test_console_exporter.py',
                'code.function': 'test_verbose_attributes',
                'name': 'world',
                'd': '{"a":1,"b":2}',
                'logfire.json_schema': '{"type":"object","properties":{"name":{},"d":{"type":"object"}}}',
            },
            events=None,
            resource=None,
        )
    ]
    out = io.StringIO()
    SimpleConsoleSpanExporter(output=out, verbose=True, colors='never').export(spans)  # type: ignore
    lines = [line.rstrip(' ') for line in out.getvalue().splitlines()]
    assert lines == [
        '00:00:01.000 Hello world!',
        '             │ test_console_exporter.py:123 info',
        "             │ name='world'",
        '             │ d={',
        "             │       'a': 1,",
        "             │       'b': 2,",
        '             │   }',
    ]

    out = io.StringIO()
    SimpleConsoleSpanExporter(output=out, verbose=True, colors='never', include_timestamp=False).export(spans)  # type: ignore
    lines = [line.rstrip(' ') for line in out.getvalue().splitlines()]
    assert lines == [
        'Hello world!',
        '│ test_console_exporter.py:123 info',
        "│ name='world'",
        '│ d={',
        "│       'a': 1,",
        "│       'b': 2,",
        '│   }',
    ]

    out = io.StringIO()
    SimpleConsoleSpanExporter(output=out, verbose=True, colors='always').export(spans)  # type: ignore
    # insert_assert(out.getvalue().splitlines())
    assert out.getvalue().splitlines() == [
        '\x1b[32m00:00:01.000\x1b[0m Hello world!',
        '             \x1b[34m│\x1b[0m \x1b[36mtest_console_exporter.py:123\x1b[0m info',
        "             \x1b[34m│ \x1b[0m\x1b[34mname=\x1b[0m\x1b[93;49m'\x1b[0m\x1b[93;49mworld\x1b[0m\x1b[93;49m'\x1b[0m",
        '             \x1b[34m│ \x1b[0m\x1b[34md=\x1b[0m\x1b[97;49m{\x1b[0m          ',
        "             \x1b[34m│ \x1b[0m  \x1b[97;49m    \x1b[0m\x1b[93;49m'\x1b[0m\x1b[93;49ma\x1b[0m\x1b[93;49m'\x1b[0m\x1b[97;49m:\x1b[0m\x1b[97;49m \x1b[0m\x1b[37;49m1\x1b[0m\x1b[97;49m,\x1b[0m",
        "             \x1b[34m│ \x1b[0m  \x1b[97;49m    \x1b[0m\x1b[93;49m'\x1b[0m\x1b[93;49mb\x1b[0m\x1b[93;49m'\x1b[0m\x1b[97;49m:\x1b[0m\x1b[97;49m \x1b[0m\x1b[37;49m2\x1b[0m\x1b[97;49m,\x1b[0m",
        '             \x1b[34m│ \x1b[0m  \x1b[97;49m}\x1b[0m          ',
    ]


def test_tags(exporter: TestExporter):
    logfire.with_tags('tag1', 'tag2').info('Hello')
    spans = exported_spans_as_models(exporter)
    # insert_assert(spans)
    assert spans == [
        ReadableSpanModel(
            name='Hello',
            context=SpanContextModel(trace_id=1, span_id=1, is_remote=False),
            parent=None,
            start_time=1000000000,
            end_time=1000000000,
            attributes={
                'logfire.span_type': 'log',
                'logfire.level_num': 9,
                'logfire.msg_template': 'Hello',
                'logfire.msg': 'Hello',
                'code.lineno': 123,
                'code.filepath': 'test_console_exporter.py',
                'code.function': 'test_tags',
                'logfire.tags': ('tag1', 'tag2'),
            },
            events=None,
            resource=None,
        )
    ]
    out = io.StringIO()
    SimpleConsoleSpanExporter(output=out, colors='never').export(spans)  # type: ignore
    # insert_assert(out.getvalue())
    assert out.getvalue() == '00:00:01.000 Hello [tag1,tag2]\n'

    out = io.StringIO()
    SimpleConsoleSpanExporter(output=out, colors='always').export(spans)  # type: ignore
    # insert_assert(out.getvalue())
    assert out.getvalue() == '\x1b[32m00:00:01.000\x1b[0m Hello \x1b[36m[tag1,tag2]\x1b[0m\n'


def test_levels(exporter: TestExporter):
    logfire.trace('trace message')
    logfire.debug('debug message')
    logfire.info('info message')
    logfire.notice('notice message')
    logfire.warn('warn message')
    logfire.error('error message')
    logfire.fatal('fatal message')

    spans = exported_spans_as_models(exporter)
    # insert_assert(spans)
    assert spans == [
        ReadableSpanModel(
            name='trace message',
            context=SpanContextModel(trace_id=1, span_id=1, is_remote=False),
            parent=None,
            start_time=1000000000,
            end_time=1000000000,
            attributes={
                'logfire.span_type': 'log',
                'logfire.level_num': 1,
                'logfire.msg_template': 'trace message',
                'logfire.msg': 'trace message',
                'code.lineno': 123,
                'code.filepath': 'test_console_exporter.py',
                'code.function': 'test_levels',
            },
            events=None,
            resource=None,
        ),
        ReadableSpanModel(
            name='debug message',
            context=SpanContextModel(trace_id=2, span_id=2, is_remote=False),
            parent=None,
            start_time=2000000000,
            end_time=2000000000,
            attributes={
                'logfire.span_type': 'log',
                'logfire.level_num': 5,
                'logfire.msg_template': 'debug message',
                'logfire.msg': 'debug message',
                'code.lineno': 123,
                'code.filepath': 'test_console_exporter.py',
                'code.function': 'test_levels',
            },
            events=None,
            resource=None,
        ),
        ReadableSpanModel(
            name='info message',
            context=SpanContextModel(trace_id=3, span_id=3, is_remote=False),
            parent=None,
            start_time=3000000000,
            end_time=3000000000,
            attributes={
                'logfire.span_type': 'log',
                'logfire.level_num': 9,
                'logfire.msg_template': 'info message',
                'logfire.msg': 'info message',
                'code.lineno': 123,
                'code.filepath': 'test_console_exporter.py',
                'code.function': 'test_levels',
            },
            events=None,
            resource=None,
        ),
        ReadableSpanModel(
            name='notice message',
            context=SpanContextModel(trace_id=4, span_id=4, is_remote=False),
            parent=None,
            start_time=4000000000,
            end_time=4000000000,
            attributes={
                'logfire.span_type': 'log',
                'logfire.level_num': 10,
                'logfire.msg_template': 'notice message',
                'logfire.msg': 'notice message',
                'code.lineno': 123,
                'code.filepath': 'test_console_exporter.py',
                'code.function': 'test_levels',
            },
            events=None,
            resource=None,
        ),
        ReadableSpanModel(
            name='warn message',
            context=SpanContextModel(trace_id=5, span_id=5, is_remote=False),
            parent=None,
            start_time=5000000000,
            end_time=5000000000,
            attributes={
                'logfire.span_type': 'log',
                'logfire.level_num': 13,
                'logfire.msg_template': 'warn message',
                'logfire.msg': 'warn message',
                'code.lineno': 123,
                'code.filepath': 'test_console_exporter.py',
                'code.function': 'test_levels',
            },
            events=None,
            resource=None,
        ),
        ReadableSpanModel(
            name='error message',
            context=SpanContextModel(trace_id=6, span_id=6, is_remote=False),
            parent=None,
            start_time=6000000000,
            end_time=6000000000,
            attributes={
                'logfire.span_type': 'log',
                'logfire.level_num': 17,
                'logfire.msg_template': 'error message',
                'logfire.msg': 'error message',
                'code.lineno': 123,
                'code.filepath': 'test_console_exporter.py',
                'code.function': 'test_levels',
            },
            events=None,
            resource=None,
        ),
        ReadableSpanModel(
            name='fatal message',
            context=SpanContextModel(trace_id=7, span_id=7, is_remote=False),
            parent=None,
            start_time=7000000000,
            end_time=7000000000,
            attributes={
                'logfire.span_type': 'log',
                'logfire.level_num': 21,
                'logfire.msg_template': 'fatal message',
                'logfire.msg': 'fatal message',
                'code.lineno': 123,
                'code.filepath': 'test_console_exporter.py',
                'code.function': 'test_levels',
            },
            events=None,
            resource=None,
        ),
    ]

    out = io.StringIO()
    SimpleConsoleSpanExporter(output=out, colors='never').export(spans)  # type: ignore
    # insert_assert(out.getvalue().splitlines())
    assert out.getvalue().splitlines() == [
        '00:00:01.000 trace message',
        '00:00:02.000 debug message',
        '00:00:03.000 info message',
        '00:00:04.000 notice message',
        '00:00:05.000 warn message',
        '00:00:06.000 error message',
        '00:00:07.000 fatal message',
    ]

    out = io.StringIO()
    SimpleConsoleSpanExporter(output=out, colors='never', verbose=True).export(spans)  # type: ignore
    # insert_assert(out.getvalue().splitlines())
    assert out.getvalue().splitlines() == [
        '00:00:01.000 trace message',
        '             │ test_console_exporter.py:123 trace',
        '00:00:02.000 debug message',
        '             │ test_console_exporter.py:123 debug',
        '00:00:03.000 info message',
        '             │ test_console_exporter.py:123 info',
        '00:00:04.000 notice message',
        '             │ test_console_exporter.py:123 notice',
        '00:00:05.000 warn message',
        '             │ test_console_exporter.py:123 warn',
        '00:00:06.000 error message',
        '             │ test_console_exporter.py:123 error',
        '00:00:07.000 fatal message',
        '             │ test_console_exporter.py:123 fatal',
    ]

    out = io.StringIO()
    SimpleConsoleSpanExporter(output=out, colors='always').export(spans)  # type: ignore
    # insert_assert(out.getvalue().splitlines())
    assert out.getvalue().splitlines() == [
        '\x1b[32m00:00:01.000\x1b[0m trace message',
        '\x1b[32m00:00:02.000\x1b[0m debug message',
        '\x1b[32m00:00:03.000\x1b[0m info message',
        '\x1b[32m00:00:04.000\x1b[0m notice message',
        '\x1b[32m00:00:05.000\x1b[0m \x1b[33mwarn message\x1b[0m',
        '\x1b[32m00:00:06.000\x1b[0m \x1b[31merror message\x1b[0m',
        '\x1b[32m00:00:07.000\x1b[0m \x1b[31mfatal message\x1b[0m',
    ]


def test_console_logging_to_stdout(capsys: pytest.CaptureFixture[str]):
    # This is essentially a basic integration test, the other tests using an exporter
    # missed that console logging had stopped working entirely for spans.

    logfire.configure(
        send_to_logfire=False,
        console=ConsoleOptions(colors='never', include_timestamps=False),
    )

    with logfire.span('outer span'):
        with logfire.span('inner span'):
            logfire.info('inner span log message')
        logfire.info('outer span log message')

    # insert_assert(capsys.readouterr().out.splitlines())
    assert capsys.readouterr().out.splitlines() == [
        'outer span',
        '  inner span',
        '    inner span log message',
        '  outer span log message',
    ]
