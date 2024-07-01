from .._internal.constants import ATTRIBUTES_LOGGING_ARGS_KEY as ATTRIBUTES_LOGGING_ARGS_KEY, ATTRIBUTES_MESSAGE_KEY as ATTRIBUTES_MESSAGE_KEY, ATTRIBUTES_MESSAGE_TEMPLATE_KEY as ATTRIBUTES_MESSAGE_TEMPLATE_KEY
from .logging import LogfireLoggingHandler as LogfireLoggingHandler
from logging import LogRecord
from typing import Any

class LogfireHandler(LogfireLoggingHandler):
    """A loguru handler that sends logs to **Logfire**."""
    custom_scope_suffix: str
    def fill_attributes(self, record: LogRecord) -> dict[str, Any]:
        """Fill attributes from a log record.

        It filters out the 'extra' attribute and adds it's content to the attributes.

        Args:
            record: The log record.

        Returns:
            The attributes for the log record.
        """
