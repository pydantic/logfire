from typing import Any

import pytest
from inline_snapshot import snapshot
from opentelemetry._logs import LogRecord, get_logger
from opentelemetry.sdk._logs import LogRecordProcessor, ReadWriteLogRecord
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.trace import ReadableSpan, SpanProcessor
from opentelemetry.trace import Span

import logfire
from logfire.testing import CaptureLogfire, IncrementalIdGenerator, TestExporter, TimeGenerator


class _RecordingSpanProcessor(SpanProcessor):
    def __init__(self) -> None:
        self.spans: list[ReadableSpan] = []

    def on_start(self, span: Span, parent_context: Any = None) -> None:
        self.spans.append(span)  # type: ignore[arg-type]

    def on_end(self, span: ReadableSpan) -> None:
        pass

    def shutdown(self) -> None:
        pass

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return True


class _RecordingLogRecordProcessor(LogRecordProcessor):
    def __init__(self) -> None:
        self.records: list[ReadWriteLogRecord] = []

    def on_emit(self, log_record: ReadWriteLogRecord) -> None:
        self.records.append(log_record)

    def shutdown(self) -> None:
        pass

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return True


def test_reset_exported_spans(exporter: TestExporter) -> None:
    assert len(exporter.exported_spans) == 0

    logfire.info('First log!')
    assert len(exporter.exported_spans) == 1
    assert exporter.exported_spans[0].name == 'First log!'

    logfire.info('Second log!')
    assert len(exporter.exported_spans) == 2
    assert exporter.exported_spans[1].name == 'Second log!'

    exporter.clear()
    assert len(exporter.exported_spans) == 0

    logfire.info('Third log!')
    assert len(exporter.exported_spans) == 1
    assert exporter.exported_spans[0].name == 'Third log!'


def test_capfire_fixture(capfire: CaptureLogfire) -> None:
    with pytest.raises(Exception):
        with logfire.span('a span!'):
            logfire.info('a log!')
            raise Exception('an exception!')

    exporter = capfire.exporter
    assert exporter.exported_spans_as_dict() == snapshot(
        [
            {
                'name': 'a log!',
                'context': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 2000000000,
                'end_time': 2000000000,
                'attributes': {
                    'logfire.span_type': 'log',
                    'logfire.level_num': 9,
                    'logfire.msg_template': 'a log!',
                    'logfire.msg': 'a log!',
                    'code.filepath': 'test_testing.py',
                    'code.function': 'test_capfire_fixture',
                    'code.lineno': 123,
                },
            },
            {
                'name': 'a span!',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 4000000000,
                'attributes': {
                    'code.filepath': 'test_testing.py',
                    'code.function': 'test_capfire_fixture',
                    'code.lineno': 123,
                    'logfire.msg_template': 'a span!',
                    'logfire.msg': 'a span!',
                    'logfire.span_type': 'span',
                    'logfire.level_num': 17,
                    'logfire.exception.fingerprint': '0000000000000000000000000000000000000000000000000000000000000000',
                },
                'events': [
                    {
                        'name': 'exception',
                        'timestamp': 3000000000,
                        'attributes': {
                            'exception.type': 'Exception',
                            'exception.message': 'an exception!',
                            'exception.stacktrace': 'Exception: an exception!',
                            'exception.escaped': 'True',
                        },
                    }
                ],
            },
        ]
    )


def test_time_generator():
    t = TimeGenerator()
    assert t() == 1000000000
    assert t() == 2000000000
    assert repr(t) == 'TimeGenerator(ns_time=2000000000)'


def test_reconfigure_preserves_span_exporter(capfire: CaptureLogfire) -> None:
    logfire.info('before')

    capfire.reconfigure(min_level='error')

    logfire.error('after')

    names = [span.name for span in capfire.exporter.exported_spans]
    assert names == ['before', 'after']


def test_reconfigure_preserves_id_and_timestamp_generators(capfire: CaptureLogfire) -> None:
    with logfire.span('before'):
        pass

    capfire.reconfigure()

    with logfire.span('after'):
        pass

    spans = capfire.exporter.exported_spans_as_dict()
    assert spans[0]['context']['trace_id'] == 1
    assert spans[1]['context']['trace_id'] == 2
    assert spans[0]['start_time'] == 1000000000
    assert spans[1]['start_time'] == 3000000000


def test_reconfigure_extends_additional_span_processors(capfire: CaptureLogfire) -> None:
    extra = _RecordingSpanProcessor()

    capfire.reconfigure(additional_span_processors=[extra])

    logfire.info('hi')

    assert len(capfire.exporter.exported_spans) == 1
    assert len(extra.spans) == 1
    assert capfire.exporter.exported_spans[0].name == 'hi'


def test_reconfigure_extends_log_record_processors(capfire: CaptureLogfire) -> None:
    extra = _RecordingLogRecordProcessor()

    capfire.reconfigure(advanced=logfire.AdvancedOptions(log_record_processors=[extra]))

    get_logger(__name__).emit(LogRecord(attributes={'event.name': 'hi'}))

    assert len(capfire.log_exporter.get_finished_logs()) == 1
    assert len(extra.records) == 1


def test_reconfigure_extends_metrics_additional_readers(capfire: CaptureLogfire) -> None:
    extra = InMemoryMetricReader()

    capfire.reconfigure(metrics=logfire.MetricsOptions(additional_readers=[extra]))

    logfire.metric_counter('a_counter').add(1)
    capfire.metrics_reader.collect()
    extra.collect()

    assert capfire.metrics_reader.get_metrics_data() is not None
    assert extra.get_metrics_data() is not None


def test_reconfigure_swaps_metrics_reader(capfire: CaptureLogfire) -> None:
    old_reader = capfire.metrics_reader

    capfire.reconfigure()

    assert capfire.metrics_reader is not old_reader


def test_reconfigure_metrics_false(capfire: CaptureLogfire) -> None:
    capfire.reconfigure(metrics=False)

    logfire.metric_counter('a_counter').add(1)
    capfire.metrics_reader.collect()

    assert capfire.metrics_reader.get_metrics_data() is None


def test_reconfigure_replaces_scrubbing(capfire: CaptureLogfire) -> None:
    capfire.reconfigure(scrubbing=False)

    logfire.info('hi', password='hunter2')

    span = capfire.exporter.exported_spans_as_dict()[0]
    assert span['attributes']['password'] == 'hunter2'


def test_reconfigure_accepts_console_and_send_to_logfire_kwargs(capfire: CaptureLogfire) -> None:
    capfire.reconfigure(console=False, send_to_logfire=False)

    logfire.info('hi')

    assert len(capfire.exporter.exported_spans) == 1


def test_reconfigure_updates_id_generator_when_overridden(capfire: CaptureLogfire) -> None:
    new_generator = IncrementalIdGenerator()
    assert capfire.id_generator is not new_generator

    capfire.reconfigure(advanced=logfire.AdvancedOptions(id_generator=new_generator))

    assert capfire.id_generator is new_generator


def test_reconfigure_updates_ns_timestamp_generator_when_overridden(capfire: CaptureLogfire) -> None:
    new_generator = TimeGenerator(ns_time=42)
    assert capfire.ns_timestamp_generator is not new_generator

    capfire.reconfigure(advanced=logfire.AdvancedOptions(ns_timestamp_generator=new_generator))

    assert capfire.ns_timestamp_generator is new_generator


def test_reconfigure_keeps_default_id_generator_when_advanced_omits_it(capfire: CaptureLogfire) -> None:
    original = capfire.id_generator

    capfire.reconfigure(advanced=logfire.AdvancedOptions())

    assert capfire.id_generator is original
