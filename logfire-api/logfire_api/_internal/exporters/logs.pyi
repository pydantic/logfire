from logfire._internal.exporters.wrapper import WrapperLogProcessor as WrapperLogProcessor
from logfire._internal.utils import is_instrumentation_suppressed as is_instrumentation_suppressed
from opentelemetry.sdk._logs import LogData

class CheckSuppressInstrumentationLogProcessorWrapper(WrapperLogProcessor):
    """Checks if instrumentation is suppressed, then suppresses instrumentation itself.

    Placed at the root of the tree of processors.
    """
    def emit(self, log_data: LogData): ...
