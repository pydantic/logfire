from __future__ import annotations

import contextlib
import inspect
import warnings
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any, Callable, TypeVar

from opentelemetry.util import types as otel_types
from typing_extensions import LiteralString, ParamSpec

from .constants import ATTRIBUTES_MESSAGE_TEMPLATE_KEY, ATTRIBUTES_TAGS_KEY
from .stack_info import get_filepath_attribute
from .utils import safe_repr, uniquify_sequence

if TYPE_CHECKING:
    from .main import Logfire


P = ParamSpec('P')
R = TypeVar('R')


def instrument(
    logfire: Logfire, tags: Sequence[str], msg_template: LiteralString | None, span_name: str | None, extract_args: bool
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        if inspect.isasyncgenfunction(func):
            raise ValueError('You cannot instrument an async generator function')

        final_span_name, attributes = arg_values(func, msg_template, span_name, tags)
        sig = inspect.signature(func)

        def open_span(*func_args: P.args, **func_kwargs: P.kwargs):
            if extract_args:
                return logfire._instrument_span_with_args(  # type: ignore
                    final_span_name, attributes, sig.bind(*func_args, **func_kwargs).arguments
                )
            else:
                return logfire._fast_span(final_span_name, attributes)  # type: ignore

        if inspect.isgeneratorfunction(func):
            warnings.warn('Instrumenting a generator function is not recommended', stacklevel=2)

            def wrapper(*func_args: P.args, **func_kwargs: P.kwargs):  # type: ignore
                with open_span(*func_args, **func_kwargs):
                    yield from func(*func_args, **func_kwargs)
        elif inspect.iscoroutinefunction(func):

            async def wrapper(*func_args: P.args, **func_kwargs: P.kwargs) -> R:  # type: ignore
                with open_span(*func_args, **func_kwargs):
                    return await func(*func_args, **func_kwargs)
        else:

            def wrapper(*func_args: P.args, **func_kwargs: P.kwargs) -> R:
                with open_span(*func_args, **func_kwargs):
                    return func(*func_args, **func_kwargs)

        return wrapper  # type: ignore

    return decorator


def arg_values(
    func: Any, msg_template: str | None, span_name: str | None, tags: Sequence[str] | None
) -> tuple[str, dict[str, otel_types.AttributeValue]]:
    func = inspect.unwrap(func)
    if not inspect.isfunction(func) and hasattr(func, '__call__'):
        func = func.__call__
    func_name = getattr(func, '__qualname__', getattr(func, '__name__', safe_repr(func)))
    if not msg_template:
        try:
            msg_template = f'Calling {inspect.getmodule(func).__name__}.{func_name}'  # type: ignore
        except Exception:  # pragma: no cover
            msg_template = f'Calling {func_name}'
    attributes: dict[str, otel_types.AttributeValue] = {
        'code.function': func_name,
        ATTRIBUTES_MESSAGE_TEMPLATE_KEY: msg_template,
    }
    with contextlib.suppress(Exception):
        attributes['code.lineno'] = func.__code__.co_firstlineno
    with contextlib.suppress(Exception):
        attributes.update(get_filepath_attribute(inspect.getsourcefile(func)))  # type: ignore

    span_name = span_name or msg_template

    if tags:
        attributes[ATTRIBUTES_TAGS_KEY] = uniquify_sequence(tags)

    return span_name, attributes
