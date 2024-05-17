"""Integration with Loguru."""

from __future__ import annotations

import inspect
import warnings
from logging import LogRecord
from typing import Any

from loguru import logger

from .._internal.constants import ATTRIBUTES_LOGGING_ARGS_KEY, ATTRIBUTES_MESSAGE_KEY, ATTRIBUTES_MESSAGE_TEMPLATE_KEY
from .logging import LogfireLoggingHandler


class LogfireHandler(LogfireLoggingHandler):
    """A loguru handler that sends logs to **Logfire**."""

    custom_scope_suffix = 'loguru'

    def fill_attributes(self, record: LogRecord) -> dict[str, Any]:
        """Fill attributes from a log record.

        It filters out the 'extra' attribute and adds it's content to the attributes.

        Args:
            record: The log record.

        Returns:
            The attributes for the log record.
        """
        attributes = super().fill_attributes(record)
        attributes.update(attributes.pop('extra', {}))
        assert not record.args

        if _LOG_METHOD_CODE:  # pragma: no branch
            frame = inspect.currentframe()
            while frame:  # pragma: no branch
                if frame.f_code is _LOG_METHOD_CODE:
                    msg_template = frame.f_locals.get('message')
                    if msg_template is not None:
                        attributes[ATTRIBUTES_MESSAGE_TEMPLATE_KEY] = msg_template
                    else:  # pragma: no cover
                        _warn_inspection_failure()

                    args = frame.f_locals.get('args')
                    if isinstance(args, (tuple, list)):
                        if args:
                            attributes[ATTRIBUTES_LOGGING_ARGS_KEY] = args
                    else:  # pragma: no cover
                        _warn_inspection_failure()

                    if record.exc_info:
                        original_record = frame.f_locals.get('log_record')
                        if isinstance(original_record, dict):
                            message = original_record.get('message')  # type: ignore
                            if isinstance(message, str) and record.msg.startswith(
                                message + '\nTraceback (most recent call last):'
                            ):
                                # `record.msg` includes a traceback added by Loguru,
                                # replace it with the original message.
                                attributes[ATTRIBUTES_MESSAGE_KEY] = message
                            else:  # pragma: no cover
                                _warn_inspection_failure()
                        else:  # pragma: no cover
                            _warn_inspection_failure()

                    break

                frame = frame.f_back

        return attributes


def _warn_inspection_failure() -> None:  # pragma: no cover
    warnings.warn(
        'Failed to extract info from loguru logger. '
        'This may affect span names and/or positional arguments. '
        'Please report an issue to logfire.',
        RuntimeWarning,
    )


try:
    _LOG_METHOD_CODE = inspect.unwrap(type(logger)._log).__code__  # type: ignore
except Exception:  # pragma: no cover
    _LOG_METHOD_CODE = None  # type: ignore
    _warn_inspection_failure()
