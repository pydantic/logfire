from dataclasses import dataclass

from opentelemetry.attributes import BoundedAttributes
from opentelemetry.sdk._logs import ReadWriteLogRecord

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
            event_name = getattr(log_record.log_record, 'event_name', None)
            if isinstance(event_name, str):
                log_record.log_record.event_name = self.scrubber.transform_log_event_name(event_name)
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
