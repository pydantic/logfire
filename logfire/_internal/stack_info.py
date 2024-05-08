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


def get_caller_stack_info(stack_offset: int = 3) -> StackInfo:
    """Get the stack info of the caller.

    This is used to bind the caller's stack info to logs and spans.

    Args:
        stack_offset: The stack level to get the info from.

    Returns:
        A dictionary of stack info attributes.
    """
    try:
        frame = inspect.currentframe()
        if frame is None:  # pragma: no cover
            return {}
        # traverse stack_level frames up
        for _ in range(stack_offset):
            frame = frame.f_back
            if frame is None:  # pragma: no cover
                return {}
        return get_stack_info_from_frame(frame)
    except Exception:  # pragma: no cover
        return {}


def get_user_stack_offset() -> int:
    """Get the stack offset of the user code.

    We want to skip the internal code, and third party code, and get the user code stack info.

    Returns:
        The stack offset of the user code.
    """
    stack_offset = 2
    try:
        frame = inspect.currentframe()
        while frame and not is_user_filename(frame.f_code.co_filename):
            frame = frame.f_back
            stack_offset += 1
    except Exception:  # pragma: no cover
        pass
    return stack_offset


@lru_cache(maxsize=2048)
def is_user_filename(filename: str) -> bool:
    """Check if the filename is a user filename.

    Args:
        filename: The filename to check.

    Returns:
        True if the filename is a user filename, False otherwise.
    """
    return not filename.startswith(PREFIXES)
