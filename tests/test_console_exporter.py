import io

import pytest
import structlog
from dirty_equals import IsInstance
from opentelemetry import trace
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from structlog.testing import LogCapture

from logfire import Logfire
from logfire.config import LogfireConfig
from logfire.exporters.console import ConsoleSpanExporter


@pytest.fixture(name='log_output')
def fixture_log_output():
    return LogCapture()


@pytest.fixture(autouse=True)
def fixture_configure_structlog(log_output: LogCapture):
    structlog.configure(processors=[log_output])


def test_console_exporter(log_output: LogCapture) -> None:
    output = io.StringIO()
    provider = TracerProvider(resource=Resource(attributes={SERVICE_NAME: 'test'}))
    processor = SimpleSpanProcessor(ConsoleSpanExporter(output=output))
    provider.add_span_processor(processor)
    trace.set_tracer_provider(provider)
    tracer = trace.get_tracer(__name__)

    with tracer.start_as_current_span('rootSpan'):
        with tracer.start_as_current_span('childSpan'):
            ...

    assert log_output.entries == [
        {'event': 'childSpan', 'indent': 0, 'log_level': 'info', 'span': IsInstance(ReadableSpan), 'verbose': True},
        {'event': 'rootSpan', 'indent': 0, 'log_level': 'info', 'span': IsInstance(ReadableSpan), 'verbose': True},
    ]


def test_logfire_with_console_exporter(log_output: LogCapture, config: LogfireConfig) -> None:
    exporter = ConsoleSpanExporter()
    logfire = Logfire(LogfireConfig.from_exports(exporter, service_name='logfire-sdk-testing'))

    @logfire.instrument('hello-world {a=}')
    def hello_world(a: int) -> None:
        logfire.tags('tag1', 'tag2').info('aha {i}', i=0)
        logfire.tags('tag1', 'tag2').info('aha {i}', i=1)

        with logfire.span('more stuff', span_name='nested-span1'):
            logfire.warning('this is a warning')
            with logfire.span('more stuff', span_name='nested-span2'):
                logfire.warning('this is another warning')

    hello_world(123)
    logfire._config.provider.force_flush()
    assert log_output.entries == [
        {
            'event': 'hello-world a=123',
            'indent': 0,
            'log_level': 'info',
            'span': IsInstance(ReadableSpan),
            'verbose': True,
        },
        {'event': 'aha 0', 'indent': 1, 'log_level': 'info', 'span': IsInstance(ReadableSpan), 'verbose': True},
        {'event': 'aha 1', 'indent': 1, 'log_level': 'info', 'span': IsInstance(ReadableSpan), 'verbose': True},
        {'event': 'more stuff', 'indent': 1, 'log_level': 'info', 'span': IsInstance(ReadableSpan), 'verbose': True},
        {
            'event': 'this is a warning',
            'indent': 2,
            'log_level': 'info',
            'span': IsInstance(ReadableSpan),
            'verbose': True,
        },
        {'event': 'more stuff', 'indent': 2, 'log_level': 'info', 'span': IsInstance(ReadableSpan), 'verbose': True},
        {
            'event': 'this is another warning',
            'indent': 3,
            'log_level': 'info',
            'span': IsInstance(ReadableSpan),
            'verbose': True,
        },
    ]
