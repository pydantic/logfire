import io
import math
import statistics
from contextlib import ExitStack

import pytest
import structlog
from dirty_equals import IsInstance
from opentelemetry import trace
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from structlog.testing import LogCapture

from logfire import install_automatic_instrumentation, uninstall_automatic_instrumentation
from logfire.exporters.console import ConsoleSpanExporter

from .module_used_for_tests import wrap


@pytest.fixture(name='log_output')
def fixture_log_output():
    return LogCapture()


@pytest.fixture(autouse=True)
def fixture_configure_structlog(log_output: LogCapture):
    structlog.configure(processors=[log_output])


def foo(x: int) -> int:
    return int(statistics.mean([math.sin(x) * 10]))


def test_auto_instrumentation_no_filter(log_output: LogCapture) -> None:
    output = io.StringIO()
    provider = TracerProvider(resource=Resource(attributes={SERVICE_NAME: 'test'}))
    processor = SimpleSpanProcessor(ConsoleSpanExporter(output=output))
    provider.add_span_processor(processor)
    trace.set_tracer_provider(provider)

    with ExitStack() as stack:
        stack.callback(uninstall_automatic_instrumentation)

        install_automatic_instrumentation()

        wrap(foo, 1)

        uninstall_automatic_instrumentation()

    # note that math.sin is included because it's a built in / C function
    assert log_output.entries == [
        {'span': IsInstance(ReadableSpan), 'verbose': True, 'indent': 0, 'event': 'time.sleep', 'log_level': 'info'},
        {'span': IsInstance(ReadableSpan), 'verbose': True, 'indent': 0, 'event': 'math.sin', 'log_level': 'info'},
        {
            'span': IsInstance(ReadableSpan),
            'verbose': True,
            'indent': 0,
            'event': 'tests.test_auto_instrumentation.foo',
            'log_level': 'info',
        },
        {
            'span': IsInstance(ReadableSpan),
            'verbose': True,
            'indent': 0,
            'event': 'tests.module_used_for_tests.wrap',
            'log_level': 'info',
        },
    ]


def test_auto_instrumentation_filter_modules(log_output: LogCapture) -> None:
    output = io.StringIO()
    provider = TracerProvider(resource=Resource(attributes={SERVICE_NAME: 'test'}))
    processor = SimpleSpanProcessor(ConsoleSpanExporter(output=output))
    provider.add_span_processor(processor)
    trace.set_tracer_provider(provider)

    with ExitStack() as stack:
        stack.callback(uninstall_automatic_instrumentation)

        install_automatic_instrumentation(modules=['tests.test_auto_instrumentation'])

        wrap(foo, 1)

        uninstall_automatic_instrumentation()

    # insert_assert(log_output.entries)
    assert log_output.entries == [
        {'span': IsInstance(ReadableSpan), 'verbose': True, 'indent': 0, 'event': 'math.sin', 'log_level': 'info'},
        {
            'span': IsInstance(ReadableSpan),
            'verbose': True,
            'indent': 0,
            'event': 'tests.test_auto_instrumentation.foo',
            'log_level': 'info',
        },
    ]
