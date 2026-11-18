from collections.abc import Sequence
from dataclasses import dataclass
from time import monotonic_ns
from typing import cast

from opentelemetry.attributes import BoundedAttributes
from opentelemetry.sdk._logs import LogRecordLimits, LogRecordProcessor, ReadableLogRecord, ReadWriteLogRecord
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor, LogRecordExporter, LogRecordExportResult

import logfire
from logfire._internal.constants import ATTRIBUTES_MESSAGE_KEY
from logfire._internal.exporters.wrapper import WrapperLogProcessor
from logfire._internal.scrubbing import BaseScrubber
from logfire._internal.utils import handle_internal_errors, is_instrumentation_suppressed


class CheckSuppressInstrumentationLogProcessorWrapper(WrapperLogProcessor):
    """Checks if instrumentation is suppressed, then suppresses instrumentation itself.

    Placed at the root of the tree of processors.
    """

    def on_emit(self, log_record: ReadWriteLogRecord):
        if is_instrumentation_suppressed():
            return None
        with logfire.suppress_instrumentation():
            return super().on_emit(log_record)


@dataclass
class MainLogProcessorWrapper(WrapperLogProcessor):
    scrubber: BaseScrubber

    def on_emit(self, log_record: ReadWriteLogRecord):
        log_record.log_record = self.scrubber.scrub_log(log_record.log_record)
        with handle_internal_errors:
            attributes = log_record.log_record.attributes
            if attributes is not None and isinstance(message := attributes.get(ATTRIBUTES_MESSAGE_KEY), str):
                transformed = self.scrubber.transform_message(message)
                if transformed != message:
                    if isinstance(attributes, BoundedAttributes):
                        # Older OTel versions need extended_attributes for structured log attributes.
                        log_record.log_record.attributes = BoundedAttributes(  # pyright: ignore[reportDeprecated]
                            attributes={**attributes, ATTRIBUTES_MESSAGE_KEY: transformed},
                            maxlen=attributes.maxlen,
                            max_value_len=attributes.max_value_len,
                            extended_attributes=True,
                        )
                    else:
                        log_record.log_record.attributes = BoundedAttributes(
                            attributes={**attributes, ATTRIBUTES_MESSAGE_KEY: transformed}
                        )
        return super().on_emit(log_record)


@dataclass
class _LogProcessorExporter(LogRecordExporter):
    """Forward drained records to a processor's `on_emit` hook.

    `BackgroundScrubbingLogProcessor` flushes and shuts down the destination processor.
    """

    processor: LogRecordProcessor

    def export(self, batch: Sequence[ReadableLogRecord]) -> LogRecordExportResult:
        with logfire.suppress_instrumentation():
            for record in batch:
                # `BatchLogRecordProcessor` always copies the limits of the emitted record.
                limits = cast(LogRecordLimits, record.limits)
                self.processor.on_emit(
                    ReadWriteLogRecord(
                        record.log_record,
                        resource=record.resource,
                        instrumentation_scope=record.instrumentation_scope,
                        limits=limits,
                    )
                )
        return LogRecordExportResult.SUCCESS

    def force_flush(self, timeout_millis: int = 30000) -> bool:  # pragma: no cover
        # `BatchLogRecordProcessor.force_flush` drains the queue and does not call this.
        return True

    def shutdown(self) -> None:
        pass


@dataclass
class BackgroundScrubbingLogProcessor(LogRecordProcessor):
    """Send each record to `processor` after a queue thread scrubs it."""

    processor: LogRecordProcessor
    scrubber: BaseScrubber

    def __post_init__(self) -> None:
        self._queue = BatchLogRecordProcessor(
            _LogProcessorExporter(MainLogProcessorWrapper(self.processor, self.scrubber)), max_export_batch_size=1
        )

    def on_emit(self, log_record: ReadWriteLogRecord) -> None:
        self._queue.on_emit(log_record)

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        # The queue drains into `processor`, so it flushes first.
        deadline = monotonic_ns() + timeout_millis * 1_000_000
        for processor in (self._queue, self.processor):
            remaining = (deadline - monotonic_ns()) // 1_000_000
            if remaining <= 0 or processor.force_flush(remaining) is False:
                return False
        return True

    def shutdown(self) -> None:
        self._queue.shutdown()
        self.processor.shutdown()
