from ..constants import ATTRIBUTES_LOG_LEVEL_NUM_KEY as ATTRIBUTES_LOG_LEVEL_NUM_KEY, ATTRIBUTES_MESSAGE_KEY as ATTRIBUTES_MESSAGE_KEY, ATTRIBUTES_MESSAGE_TEMPLATE_KEY as ATTRIBUTES_MESSAGE_TEMPLATE_KEY, ATTRIBUTES_SPAN_TYPE_KEY as ATTRIBUTES_SPAN_TYPE_KEY, LEVEL_NUMBERS as LEVEL_NUMBERS, PENDING_SPAN_NAME_SUFFIX as PENDING_SPAN_NAME_SUFFIX, log_level_attributes as log_level_attributes
from ..scrubbing import Scrubber as Scrubber
from ..utils import ReadableSpanDict as ReadableSpanDict, is_instrumentation_suppressed as is_instrumentation_suppressed, span_to_dict as span_to_dict, truncate_string as truncate_string
from .wrapper import WrapperSpanProcessor as WrapperSpanProcessor
from _typeshed import Incomplete
from opentelemetry import context as context
from opentelemetry.sdk.trace import ReadableSpan, Span as Span, SpanProcessor as SpanProcessor
from opentelemetry.sdk.util.instrumentation import InstrumentationScope as InstrumentationScope

class MainSpanProcessorWrapper(WrapperSpanProcessor):
    """Wrapper around other processors to intercept starting and ending spans with our own global logic.

    Suppresses starting/ending if the current context has a `suppress_instrumentation` value.
    Tweaks the send/receive span names generated by the ASGI middleware.
    """
    scrubber: Incomplete
    def __init__(self, processor: SpanProcessor, scrubber: Scrubber) -> None: ...
    def on_start(self, span: Span, parent_context: context.Context | None = None) -> None: ...
    def on_end(self, span: ReadableSpan) -> None: ...
