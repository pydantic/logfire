import re
from .constants import ATTRIBUTES_JSON_SCHEMA_KEY as ATTRIBUTES_JSON_SCHEMA_KEY, ATTRIBUTES_LOG_LEVEL_NAME_KEY as ATTRIBUTES_LOG_LEVEL_NAME_KEY, ATTRIBUTES_LOG_LEVEL_NUM_KEY as ATTRIBUTES_LOG_LEVEL_NUM_KEY, ATTRIBUTES_MESSAGE_KEY as ATTRIBUTES_MESSAGE_KEY, ATTRIBUTES_MESSAGE_TEMPLATE_KEY as ATTRIBUTES_MESSAGE_TEMPLATE_KEY, ATTRIBUTES_PENDING_SPAN_REAL_PARENT_KEY as ATTRIBUTES_PENDING_SPAN_REAL_PARENT_KEY, ATTRIBUTES_SAMPLE_RATE_KEY as ATTRIBUTES_SAMPLE_RATE_KEY, ATTRIBUTES_SPAN_TYPE_KEY as ATTRIBUTES_SPAN_TYPE_KEY, ATTRIBUTES_TAGS_KEY as ATTRIBUTES_TAGS_KEY, NULL_ARGS_KEY as NULL_ARGS_KEY, RESOURCE_ATTRIBUTES_PACKAGE_VERSIONS as RESOURCE_ATTRIBUTES_PACKAGE_VERSIONS
from .stack_info import STACK_INFO_KEYS as STACK_INFO_KEYS
from .utils import ReadableSpanDict as ReadableSpanDict
from _typeshed import Incomplete
from dataclasses import dataclass
from opentelemetry.sdk.trace import Event
from typing import Any, Callable, Sequence

DEFAULT_PATTERNS: Incomplete

@dataclass
class ScrubMatch:
    """An object passed to the [`scrubbing_callback`][logfire.configure(scrubbing_callback)] function."""
    path: tuple[str | int, ...]
    value: Any
    pattern_match: re.Match[str]
    def __init__(self, path, value, pattern_match) -> None: ...
ScrubCallback = Callable[[ScrubMatch], Any]

class Scrubber:
    """Redacts potentially sensitive data."""
    SAFE_KEYS: Incomplete
    def __init__(self, patterns: Sequence[str] | None, callback: ScrubCallback | None = None) -> None: ...
    def scrub_span(self, span: ReadableSpanDict): ...
    def scrub_event_attributes(self, event: Event, index: int): ...
    def scrub(self, path: tuple[str | int, ...], value: Any) -> Any:
        """Redacts sensitive data from `value`, recursing into nested sequences and mappings.

        `path` is a list of keys and indices leading to `value` in the span.
        Similar to the truncation code, it should use the field names in the frontend, e.g. `otel_events`.
        """
