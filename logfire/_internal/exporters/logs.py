from opentelemetry.sdk._logs import LogData

import logfire
from logfire._internal.exporters.wrapper import WrapperLogProcessor
from logfire._internal.utils import is_instrumentation_suppressed


class CheckSuppressInstrumentationLogProcessorWrapper(WrapperLogProcessor):
    """Checks if instrumentation is suppressed, then suppresses instrumentation itself.

    Placed at the root of the tree of processors.
    """

    def emit(self, log_data: LogData):
        if is_instrumentation_suppressed():
            return
        with logfire.suppress_instrumentation():
            return super().emit(log_data)
