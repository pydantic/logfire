from _typeshed import Incomplete
from opentelemetry.util import types as otel_types

LOGFIRE_ATTRIBUTES_NAMESPACE: str
LevelName: Incomplete
LEVEL_NUMBERS: Incomplete
NUMBER_TO_LEVEL: Incomplete
LOGGING_TO_OTEL_LEVEL_NUMBERS: Incomplete
ATTRIBUTES_LOG_LEVEL_NAME_KEY: Incomplete
ATTRIBUTES_LOG_LEVEL_NUM_KEY: Incomplete

def log_level_attributes(level: LevelName | int) -> dict[str, otel_types.AttributeValue]: ...

SpanTypeType: Incomplete
ATTRIBUTES_SPAN_TYPE_KEY: Incomplete
ATTRIBUTES_PENDING_SPAN_REAL_PARENT_KEY: Incomplete
ATTRIBUTES_TAGS_KEY: Incomplete
ATTRIBUTES_MESSAGE_TEMPLATE_KEY: Incomplete
ATTRIBUTES_MESSAGE_KEY: Incomplete
DISABLE_CONSOLE_KEY: Incomplete
ATTRIBUTES_JSON_SCHEMA_KEY: Incomplete
ATTRIBUTES_LOGGING_ARGS_KEY: Incomplete
ATTRIBUTES_VALIDATION_ERROR_KEY: str
ATTRIBUTES_SCRUBBED_KEY: Incomplete
NULL_ARGS_KEY: str
PENDING_SPAN_NAME_SUFFIX: str
LOGFIRE_BASE_URL: str
RESOURCE_ATTRIBUTES_PACKAGE_VERSIONS: str
OTLP_MAX_INT_SIZE: Incomplete
DEFAULT_FALLBACK_FILE_NAME: str
ATTRIBUTES_SAMPLE_RATE_KEY: str
CONTEXT_ATTRIBUTES_KEY: Incomplete
CONTEXT_SAMPLE_RATE_KEY: Incomplete
OTLP_MAX_BODY_SIZE: Incomplete
MESSAGE_FORMATTED_VALUE_LENGTH_LIMIT: int
ONE_SECOND_IN_NANOSECONDS: int
