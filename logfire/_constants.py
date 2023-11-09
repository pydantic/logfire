from typing import Literal

LOGFIRE_ATTRIBUTES_NAMESPACE = 'logfire'
"""Namespace within OTEL attributes used by logfire."""

ATTRIBUTES_ATTRIBUTES_KEY = f'{LOGFIRE_ATTRIBUTES_NAMESPACE}.attributes'
"""The key within OTEL attributes where logfire puts serialized attributes."""

LevelName = Literal['debug', 'info', 'notice', 'warning', 'error', 'critical']
"""Level names for records."""

ATTRIBUTES_LOG_LEVEL_KEY = f'{LOGFIRE_ATTRIBUTES_NAMESPACE}.level'
"""The key within OTEL attributes where logfire puts the log level."""

SpanTypeType = Literal['log', 'start_span', 'span']

SPAN_TYPE_ATTRIBUTE_NAME = 'span_type'
"""The key within OTEL attributes where logfire puts the span type."""

ATTRIBUTES_SPAN_TYPE_KEY = f'{LOGFIRE_ATTRIBUTES_NAMESPACE}.{SPAN_TYPE_ATTRIBUTE_NAME}'
"""Used to differentiate logs, start spans and regular spans. Absences should be interpreted as a real span."""

ATTRIBUTES_START_SPAN_REAL_PARENT_KEY = f'{LOGFIRE_ATTRIBUTES_NAMESPACE}.start_parent_id'
"""The real parent of a start span, i.e. the parent of it's corresponding span and also it's grandparent"""

ATTRIBUTES_TAGS_KEY = f'{LOGFIRE_ATTRIBUTES_NAMESPACE}.tags'
"""The key within OTEL attributes where logfire puts tags."""

ATTRIBUTES_MESSAGE_TEMPLATE_KEY = f'{LOGFIRE_ATTRIBUTES_NAMESPACE}.msg_template'
"""The message template for a log."""

ATTRIBUTES_MESSAGE_KEY = f'{LOGFIRE_ATTRIBUTES_NAMESPACE}.msg'
"""The formatted message for a log."""

ATTRIBUTES_VALIDATION_ERROR_KEY = 'exception.logfire.data'
"""The key within OTEL attributes where logfire puts validation errors."""

NON_SCALAR_VAR_SUFFIX = '__JSON'
"""Suffix added to non-scalar variables to indicate they should be serialized as JSON."""

NULL_ARGS_KEY = 'logfire.null_args'
"""Key in OTEL attributes that collects attributes with a null (None) value."""

START_SPAN_NAME_SUFFIX = ' (start)'
"""Suffix added to the name of a start span to indicate it's a start span and avoid collisions with the real span while in flight."""

LOGFIRE_BASE_URL = 'https://api.logfire.dev'
"""The Logfire API base URL."""

RESOURCE_ATTRIBUTES_PACKAGE_VERSIONS = 'logfire.package_versions'
"""Versions of installed packages, serialized as list of json objects with keys 'name' and 'version'."""

OTLP_MAX_INT_SIZE = 2**63 - 1
"""OTLP only supports signed 64-bit integers, larger integers get sent as strings."""

OTLP_LARGE_INT_SUFFIX = '__LARGE_INT'
"""Suffix added to large integers to indicate they should be serialized as strings."""

DEFAULT_FALLBACK_FILE_NAME = 'logfire_spans.bin'
"""The default name of the fallback file, used when the API is unreachable."""

# see https://github.com/open-telemetry/opentelemetry-python/blob/d054dff47d2da663a39b9656d106c3d15f344269/opentelemetry-api/src/opentelemetry/context/__init__.py#L171
SUPPRESS_INSTRUMENTATION_CONTEXT_KEY = 'suppress_instrumentation'
"""Key in OTEL context that indicates whether instrumentation should be suppressed."""

ATTRIBUTES_SAMPLE_RATE_KEY = 'logfire.sample_rate'
"""Key in OTEL context that indicates the sample rate for this span."""
