from __future__ import annotations

import warnings
from typing import Literal

from opentelemetry.context import create_key
from opentelemetry.util import types as otel_types

LOGFIRE_ATTRIBUTES_NAMESPACE = 'logfire'
"""Namespace within OTEL attributes used by logfire."""

LevelName = Literal['trace', 'debug', 'info', 'notice', 'warn', 'warning', 'error', 'fatal']
"""Level names for records."""

LEVEL_NUMBERS = {
    'trace': 1,
    'debug': 5,
    'info': 9,
    'notice': 10,
    'warn': 13,
    # warning is used by standard lib logging, has same meaning as "warn"
    'warning': 13,
    'error': 17,
    'fatal': 21,
}

ATTRIBUTES_LOG_LEVEL_NAME_KEY = f'{LOGFIRE_ATTRIBUTES_NAMESPACE}.level_name'
"""The key within OTEL attributes where logfire puts the log level name."""

ATTRIBUTES_LOG_LEVEL_NUM_KEY = f'{LOGFIRE_ATTRIBUTES_NAMESPACE}.level_num'
"""The key within OTEL attributes where logfire puts the log level number."""


# This is in this file to encourage using it instead of setting these attributes manually.
def log_level_attributes(level: LevelName) -> dict[str, otel_types.AttributeValue]:
    if level not in LEVEL_NUMBERS:
        warnings.warn(f'Invalid log level name: {level!r}')
        level = 'error'

    return {
        ATTRIBUTES_LOG_LEVEL_NAME_KEY: level,
        ATTRIBUTES_LOG_LEVEL_NUM_KEY: LEVEL_NUMBERS[level],
    }


SpanTypeType = Literal['log', 'pending_span', 'span']

ATTRIBUTES_SPAN_TYPE_KEY = f'{LOGFIRE_ATTRIBUTES_NAMESPACE}.span_type'
"""Used to differentiate logs, pending spans and regular spans. Absences should be interpreted as a real span."""

ATTRIBUTES_PENDING_SPAN_REAL_PARENT_KEY = f'{LOGFIRE_ATTRIBUTES_NAMESPACE}.pending_parent_id'
"""The real parent of a pending span, i.e. the parent of it's corresponding span and also it's grandparent"""

ATTRIBUTES_TAGS_KEY = f'{LOGFIRE_ATTRIBUTES_NAMESPACE}.tags'
"""The key within OTEL attributes where logfire puts tags."""

ATTRIBUTES_MESSAGE_TEMPLATE_KEY = f'{LOGFIRE_ATTRIBUTES_NAMESPACE}.msg_template'
"""The message template for a log."""

ATTRIBUTES_MESSAGE_KEY = f'{LOGFIRE_ATTRIBUTES_NAMESPACE}.msg'
"""The formatted message for a log."""

DISABLE_CONSOLE_KEY = f'{LOGFIRE_ATTRIBUTES_NAMESPACE}.disable_console_log'
"""special attribute to disable console logging, on a per span basis."""

ATTRIBUTES_JSON_SCHEMA_KEY = f'{LOGFIRE_ATTRIBUTES_NAMESPACE}.json_schema'
"""Key in OTEL attributes that collects the JSON schema."""

ATTRIBUTES_LOGGING_ARGS_KEY = f'{LOGFIRE_ATTRIBUTES_NAMESPACE}.logging_args'

ATTRIBUTES_VALIDATION_ERROR_KEY = 'exception.logfire.data'
"""The key within OTEL attributes where logfire puts validation errors."""

NULL_ARGS_KEY = 'logfire.null_args'
"""Key in OTEL attributes that collects attributes with a null (None) value."""

PENDING_SPAN_NAME_SUFFIX = ' (pending)'
"""Suffix added to the name of a pending span to indicate it's a pending span and avoid collisions with the real span while in flight."""

LOGFIRE_BASE_URL = 'https://api.logfire.dev'
"""The Logfire API base URL."""

RESOURCE_ATTRIBUTES_PACKAGE_VERSIONS = 'logfire.package_versions'
"""Versions of installed packages, serialized as list of json objects with keys 'name' and 'version'."""

OTLP_MAX_INT_SIZE = 2**63 - 1
"""OTLP only supports signed 64-bit integers, larger integers get sent as strings."""

DEFAULT_FALLBACK_FILE_NAME = 'logfire_spans.bin'
"""The default name of the fallback file, used when the API is unreachable."""

# see https://github.com/open-telemetry/opentelemetry-python/blob/d054dff47d2da663a39b9656d106c3d15f344269/opentelemetry-api/src/opentelemetry/context/__init__.py#L171
SUPPRESS_INSTRUMENTATION_CONTEXT_KEY = 'suppress_instrumentation'
"""Key in OTEL context that indicates whether instrumentation should be suppressed."""

ATTRIBUTES_SAMPLE_RATE_KEY = 'logfire.sample_rate'
"""Key in attributes that indicates the sample rate for this span."""

CONTEXT_ATTRIBUTES_KEY = create_key('logfire.attributes')  # note this has a random suffix that OTEL adds
"""Key in the OTEL context that contains the logfire attributes."""

CONTEXT_SAMPLE_RATE_KEY = create_key('logfire.sample-rate')  # note this has a random suffix that OTEL adds
"""Key in the OTEL context that contains the current sample rate."""

OTLP_MAX_BODY_SIZE = 1024 * 1024 * 5  # 5MB
"""Maximum body size for an OTLP request. Both our backend and SDK enforce this limit."""

MESSAGE_FORMATTED_VALUE_LENGTH_LIMIT = 128
"""Maximum number of characters for formatted values in a logfire message."""

ONE_SECOND_IN_NANOSECONDS = 1_000_000_000
