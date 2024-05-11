from __future__ import annotations

import inspect
import sys
from functools import lru_cache
from pathlib import Path
from types import CodeType, FrameType
from typing import TypedDict

import opentelemetry.sdk.trace

import logfire

_CWD = Path('.').resolve()

StackInfo = TypedDict('StackInfo', {'code.filepath': str, 'code.lineno': int, 'code.function': str}, total=False)

STACK_INFO_KEYS = set(StackInfo.__annotations__.keys())
assert STACK_INFO_KEYS == {'code.filepath', 'code.lineno', 'code.function'}

SITE_PACKAGES_DIR = str(Path(opentelemetry.sdk.trace.__file__).parent.parent.parent.parent.absolute())
PYTHON_LIB_DIR = str(Path(inspect.__file__).parent.absolute())
LOGFIRE_DIR = str(Path(logfire.__file__).parent.absolute())
PREFIXES = (SITE_PACKAGES_DIR, PYTHON_LIB_DIR, LOGFIRE_DIR)


def get_filepath_attribute(file: str) -> StackInfo:
    path = Path(file)
    if path.is_absolute():
        try:
            path = path.relative_to(_CWD)
        except ValueError:  # pragma: no cover
            # happens if filename path is not within CWD
            pass
    return {'code.filepath': str(path)}


@lru_cache(maxsize=2048)
def get_code_object_info(code: CodeType) -> StackInfo:
    result = get_filepath_attribute(code.co_filename)
    if code.co_name != '<module>':
        result['code.function'] = code.co_qualname if sys.version_info >= (3, 11) else code.co_name
    result['code.lineno'] = code.co_firstlineno
    return result


def get_stack_info_from_frame(frame: FrameType) -> StackInfo:
    return {
        **get_code_object_info(frame.f_code),
        'code.lineno': frame.f_lineno,
    }


def get_user_stack_info() -> StackInfo:
    """Get the stack info for the first calling frame in user code.

    See is_user_code for details.
    Returns an empty dict if no such frame is found.
    """
    frame, _stacklevel = get_user_frame_and_stacklevel()
    if frame:
        return get_stack_info_from_frame(frame)
    return {}


def get_user_frame_and_stacklevel() -> tuple[FrameType | None, int]:
    """Get the first calling frame in user code and a corresponding stacklevel that can be passed to `warnings.warn`.

    See is_user_code for details.
    Returns `(None, 0)` if no such frame is found.
    """
    frame = inspect.currentframe()
    stacklevel = 0
    while frame:
        if is_user_code(frame.f_code):
            return frame, stacklevel
        frame = frame.f_back
        stacklevel += 1
    return None, 0


@lru_cache(maxsize=8192)
def is_user_code(code: CodeType) -> bool:
    """Check if the code object is from user code.

    A code object is not user code if:
    - It is from a file in
        - the standard library
        - site-packages (specifically wherever opentelemetry is installed)
        - the logfire package
    - It is a list/dict/set comprehension.
        These are artificial frames only created before Python 3.12,
        and they are always called directly from the enclosing function so it makes sense to skip them.
        On the other hand, generator expressions and lambdas might be called far away from where they are defined.
    """
    return not (
        str(Path(code.co_filename).absolute()).startswith(PREFIXES)
        or code.co_name in ('<listcomp>', '<dictcomp>', '<setcomp>')
    )
