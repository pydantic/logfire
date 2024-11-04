import ast
import executing
import types
from .constants import ATTRIBUTES_SCRUBBED_KEY as ATTRIBUTES_SCRUBBED_KEY, MESSAGE_FORMATTED_VALUE_LENGTH_LIMIT as MESSAGE_FORMATTED_VALUE_LENGTH_LIMIT
from .scrubbing import BaseScrubber as BaseScrubber, NOOP_SCRUBBER as NOOP_SCRUBBER, ScrubbedNote as ScrubbedNote
from .stack_info import warn_at_user_stacklevel as warn_at_user_stacklevel
from .utils import log_internal_error as log_internal_error, truncate_string as truncate_string
from _typeshed import Incomplete
from string import Formatter
from types import CodeType as CodeType
from typing import Any, Literal
from typing_extensions import NotRequired, TypedDict

class LiteralChunk(TypedDict):
    t: Literal['lit']
    v: str

class ArgChunk(TypedDict):
    t: Literal['arg']
    v: str
    spec: NotRequired[str]

class ChunksFormatter(Formatter):
    def chunks(self, format_string: str, kwargs: dict[str, Any], *, scrubber: BaseScrubber, fstring_frame: types.FrameType | None = None) -> tuple[list[LiteralChunk | ArgChunk], dict[str, Any], str]: ...

chunks_formatter: Incomplete

def logfire_format(format_string: str, kwargs: dict[str, Any], scrubber: BaseScrubber) -> str: ...
def logfire_format_with_magic(format_string: str, kwargs: dict[str, Any], scrubber: BaseScrubber, fstring_frame: types.FrameType | None = None) -> tuple[str, dict[str, Any], str]: ...
def compile_formatted_value(node: ast.FormattedValue, ex_source: executing.Source) -> tuple[str, CodeType, CodeType]:
    """Returns three things that can be expensive to compute.

    1. Source code corresponding to the node value (excluding the format spec).
    2. A compiled code object which can be evaluated to calculate the value.
    3. Another code object which formats the value.
    """
def get_node_source_text(node: ast.AST, ex_source: executing.Source):
    """Returns some Python source code representing `node`.

    Preferably the actual original code given by `ast.get_source_segment`,
    but falling back to `ast.unparse(node)` if the former is incorrect.
    This happens sometimes due to Python bugs (especially for older Python versions)
    in the source positions of AST nodes inside f-strings.
    """
def get_stacklevel(frame: types.FrameType): ...

class InspectArgumentsFailedWarning(Warning): ...

def warn_inspect_arguments(msg: str, stacklevel: int): ...

class KnownFormattingError(Exception):
    """An error raised when there's something wrong with a format string or the field values.

    In other words this should correspond to errors that would be raised when using `str.format`,
    and generally indicate a user error, most likely that they weren't trying to pass a template string at all.
    """
class FormattingFailedWarning(UserWarning): ...

def warn_formatting(msg: str): ...
