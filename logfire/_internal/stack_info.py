from __future__ import annotations

import inspect
import sys
from functools import lru_cache
from pathlib import Path
from types import CodeType, FrameType
from typing import TypedDict, cast

import opentelemetry.sdk.trace

import logfire

_CWD = Path('.').resolve()

StackInfo = TypedDict('StackInfo', {'code.filepath': str, 'code.lineno': int, 'code.function': str}, total=False)

STACK_INFO_KEYS = set(StackInfo.__annotations__.keys())
assert STACK_INFO_KEYS == {'code.filepath', 'code.lineno', 'code.function'}

SITE_PACKAGES_DIR = str(Path(opentelemetry.sdk.trace.__file__).parent.parent.parent.parent.absolute())
LOGFIRE_DIR = str(Path(logfire.__file__).parent.absolute())
PREFIXES = (SITE_PACKAGES_DIR, LOGFIRE_DIR)


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


def get_caller_stack_info() -> StackInfo:
    """Get the stack info of the caller.

    Args:
        stack_offset: The stack level to get the info from.

    Returns:
        A dictionary of stack info attributes.
    """
    frame = cast(FrameType, inspect.currentframe())
    while frame and frame.f_back and not is_user_filename(frame.f_code.co_filename):
        frame = frame.f_back
    return get_stack_info_from_frame(frame)


def get_caller_stack_offset(caller_stack_info: StackInfo) -> int:
    """Get the stack offset of the caller.

    Args:
        caller_stack_info: The stack info of the caller.

    Returns:
        The stack offset of the caller.
    """
    frame = inspect.currentframe()
    stack_offset = 0
    while frame:
        if get_stack_info_from_frame(frame) == caller_stack_info:
            break
        frame = frame.f_back
        stack_offset += 1
    return stack_offset


@lru_cache(maxsize=2048)
def is_user_filename(filename: str) -> bool:
    """Check if the filename is a user filename.

    Args:
        filename: The filename to check.

    Returns:
        True if the filename is a user filename, False otherwise.
    """
    return not str(Path(filename).absolute()).startswith(PREFIXES)
