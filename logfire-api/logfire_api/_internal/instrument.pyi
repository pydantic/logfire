from .constants import ATTRIBUTES_MESSAGE_TEMPLATE_KEY as ATTRIBUTES_MESSAGE_TEMPLATE_KEY, ATTRIBUTES_TAGS_KEY as ATTRIBUTES_TAGS_KEY
from .main import Logfire as Logfire
from .stack_info import get_filepath_attribute as get_filepath_attribute
from .utils import safe_repr as safe_repr, uniquify_sequence as uniquify_sequence
from _typeshed import Incomplete
from collections.abc import Sequence
from opentelemetry.util import types as otel_types
from typing import Any, Callable, ContextManager, Iterable, TypeVar
from typing_extensions import LiteralString, ParamSpec

P = ParamSpec('P')
R = TypeVar('R')
CONTEXTMANAGER_HELPER_CODE: Incomplete
ASYNCCONTEXTMANAGER_HELPER_CODE: Incomplete
GENERATOR_WARNING_MESSAGE: str

def instrument(logfire: Logfire, tags: Sequence[str], msg_template: LiteralString | None, span_name: str | None, extract_args: bool | Iterable[str], allow_generator: bool) -> Callable[[Callable[P, R]], Callable[P, R]]: ...
def get_open_span(logfire: Logfire, attributes: dict[str, otel_types.AttributeValue], span_name: str | None, extract_args: bool | Iterable[str], func: Callable[P, R]) -> Callable[P, ContextManager[Any]]: ...
def get_attributes(func: Any, msg_template: str | None, tags: Sequence[str] | None) -> dict[str, otel_types.AttributeValue]: ...
