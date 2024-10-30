from _typeshed import Incomplete
from collections.abc import Generator
from dataclasses import dataclass
from logfire._internal.stack_info import is_user_code as is_user_code
from opentelemetry import trace as trace_api
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import Event as Event, ReadableSpan
from opentelemetry.sdk.trace.id_generator import IdGenerator
from opentelemetry.sdk.util.instrumentation import InstrumentationScope
from opentelemetry.trace.status import Status
from opentelemetry.util import types as otel_types
from packaging.version import Version
from pathlib import Path
from requests import RequestException, Response
from types import TracebackType
from typing import Any, Mapping, Sequence, TypeVar, TypedDict

SysExcInfo = tuple[type[BaseException], BaseException, TracebackType | None] | tuple[None, None, None]
T = TypeVar('T')
JsonValue: Incomplete
JsonDict = dict[str, JsonValue]

def dump_json(obj: JsonValue) -> str: ...

logger: Incomplete

def uniquify_sequence(seq: Sequence[T]) -> tuple[T, ...]:
    """Remove duplicates from a sequence preserving order."""
def safe_repr(obj: Any) -> str:
    """Return some kind of non-empty string representation of an object, catching exceptions."""
Truncatable = TypeVar('Truncatable', str, bytes, 'list[Any]', 'tuple[Any, ...]')

def truncate_string(s: str, *, max_length: int, middle: str = '...') -> str:
    """Return a string at most max_length characters long, with `middle` in the middle if truncated."""
def truncate_sequence(seq: Truncatable, *, max_length: int, middle: Truncatable) -> Truncatable:
    """Return a sequence at with `len()` at most `max_length`, with `middle` in the middle if truncated."""
def read_toml_file(path: Path) -> dict[str, Any]:
    """Read a TOML file and return the parsed data.

    It wraps the `tomllib.load` function from Python 3.11 or the `tomli.load` function from older versions.
    """

class ReadableSpanDict(TypedDict):
    """A dictionary representation of a ReadableSpan.

    ReadableSpan is immutable, so making modified versions of it is inconvenient and slow.
    Converting a ReadableSpan to a ReadableSpanDict using span_to_dict makes it easier to modify.
    See `SpanProcessorWrapper.on_end` for an example of how this is useful.
    """
    name: str
    context: trace_api.SpanContext | None
    parent: trace_api.SpanContext | None
    resource: Resource | None
    attributes: Mapping[str, otel_types.AttributeValue]
    events: Sequence[Event]
    links: Sequence[trace_api.Link]
    kind: trace_api.SpanKind
    status: Status
    start_time: int | None
    end_time: int | None
    instrumentation_scope: InstrumentationScope | None

def span_to_dict(span: ReadableSpan) -> ReadableSpanDict:
    """See ReadableSpanDict."""

class UnexpectedResponse(RequestException):
    """An unexpected response was received from the server."""
    def __init__(self, response: Response) -> None: ...
    @classmethod
    def raise_for_status(cls, response: Response) -> None:
        """Like the requests method, but raises a more informative exception."""

def ensure_data_dir_exists(data_dir: Path) -> None: ...
def get_version(version: str) -> Version:
    """Return a packaging.version.Version object from a version string.

    We check if `packaging` is available, falling back to `setuptools._vendor.packaging` if it's not.
    """

SUPPRESS_INSTRUMENTATION_CONTEXT_KEYS: Incomplete

def is_instrumentation_suppressed() -> bool:
    """Return True if the `suppress_instrumentation` context manager is currently active.

    This means that any logs/spans generated by logfire or OpenTelemetry will not be logged in any way.
    """
def suppress_instrumentation() -> Generator[None]:
    """Context manager to suppress all logs/spans generated by logfire or OpenTelemetry."""
def log_internal_error() -> None: ...
def handle_internal_errors() -> Generator[None]: ...
def maybe_capture_server_headers(capture: bool): ...
def is_asgi_send_receive_span_name(name: str) -> bool: ...

@dataclass(repr=True)
class SeededRandomIdGenerator(IdGenerator):
    """Generate random span/trace IDs from a seed for deterministic tests.

    Similar to RandomIdGenerator from OpenTelemetry, but with a seed.
    Set the seed to None for non-deterministic randomness.
    In that case the difference from RandomIdGenerator is that it's not affected by `random.seed(...)`.

    Trace IDs are 128-bit integers.
    Span IDs are 64-bit integers.
    """
    seed: int | None = ...
    random = ...
    def __post_init__(self) -> None: ...
    def generate_span_id(self) -> int: ...
    def generate_trace_id(self) -> int: ...
