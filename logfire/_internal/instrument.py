from __future__ import annotations

import contextlib
import functools
import inspect
import warnings
from collections.abc import Sequence
from contextlib import asynccontextmanager, contextmanager
from typing import TYPE_CHECKING, Any, Callable, ContextManager, Iterable, TypeVar

from opentelemetry.util import types as otel_types
from typing_extensions import LiteralString, ParamSpec

from .constants import ATTRIBUTES_MESSAGE_TEMPLATE_KEY, ATTRIBUTES_TAGS_KEY
from .stack_info import get_filepath_attribute
from .utils import safe_repr, uniquify_sequence

if TYPE_CHECKING:
    from .main import Logfire


P = ParamSpec('P')
R = TypeVar('R')


@contextmanager
def _cm():  # pragma: no cover
    yield


@asynccontextmanager
async def _acm():  # pragma: no cover
    yield


CONTEXTMANAGER_HELPER_CODE = getattr(_cm, '__code__', None)
ASYNCCONTEXTMANAGER_HELPER_CODE = getattr(_acm, '__code__', None)

GENERATOR_WARNING_MESSAGE = (
    '@logfire.instrument should only be used on generators if they are used as context managers. '
    'See https://logfire.pydantic.dev/docs/guides/advanced/generators/#using-logfireinstrument for more information.'
)


def instrument(
    logfire: Logfire,
    tags: Sequence[str],
    msg_template: LiteralString | None,
    span_name: str | None,
    extract_args: bool | Iterable[str],
    allow_generator: bool,
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        if getattr(func, '__code__', None) in (CONTEXTMANAGER_HELPER_CODE, ASYNCCONTEXTMANAGER_HELPER_CODE):
            warnings.warn(
                '@logfire.instrument should be underneath @contextlib.[async]contextmanager so that it is applied first.',
                stacklevel=2,
            )

        attributes = get_attributes(func, msg_template, tags)
        open_span = get_open_span(logfire, attributes, span_name, extract_args, func)

        if inspect.isgeneratorfunction(func):
            if not allow_generator:
                warnings.warn(GENERATOR_WARNING_MESSAGE, stacklevel=2)

            def wrapper(*func_args: P.args, **func_kwargs: P.kwargs):  # type: ignore
                with open_span(*func_args, **func_kwargs):
                    yield from func(*func_args, **func_kwargs)
        elif inspect.isasyncgenfunction(func):
            if not allow_generator:
                warnings.warn(GENERATOR_WARNING_MESSAGE, stacklevel=2)

            async def wrapper(*func_args: P.args, **func_kwargs: P.kwargs):  # type: ignore
                with open_span(*func_args, **func_kwargs):
                    # `yield from` is invalid syntax in an async function.
                    # This loop is not quite equivalent, because `yield from` also handles things like
                    # sending values to the subgenerator.
                    # Fixing this would at least mean porting https://peps.python.org/pep-0380/#formal-semantics
                    # which is quite messy, and it's not clear if that would be correct based on
                    # https://discuss.python.org/t/yield-from-in-async-functions/47050.
                    # So instead we have an extra warning in the docs about this.
                    async for x in func(*func_args, **func_kwargs):
                        yield x

        elif inspect.iscoroutinefunction(func):

            async def wrapper(*func_args: P.args, **func_kwargs: P.kwargs) -> R:  # type: ignore
                with open_span(*func_args, **func_kwargs):
                    return await func(*func_args, **func_kwargs)
        else:

            def wrapper(*func_args: P.args, **func_kwargs: P.kwargs) -> R:
                with open_span(*func_args, **func_kwargs):
                    return func(*func_args, **func_kwargs)

        wrapper = functools.wraps(func)(wrapper)  # type: ignore
        return wrapper

    return decorator


def get_open_span(
    logfire: Logfire,
    attributes: dict[str, otel_types.AttributeValue],
    span_name: str | None,
    extract_args: bool | Iterable[str],
    func: Callable[P, R],
) -> Callable[P, ContextManager[Any]]:
    final_span_name: str = span_name or attributes[ATTRIBUTES_MESSAGE_TEMPLATE_KEY]  # type: ignore

    # This is the fast case for when there are no arguments to extract
    def open_span(*_: P.args, **__: P.kwargs):  # type: ignore
        return logfire._fast_span(final_span_name, attributes)  # type: ignore

    if extract_args is True:
        sig = inspect.signature(func)
        if sig.parameters:  # only extract args if there are any

            def open_span(*func_args: P.args, **func_kwargs: P.kwargs):
                args_dict = sig.bind(*func_args, **func_kwargs).arguments
                return logfire._instrument_span_with_args(  # type: ignore
                    final_span_name, attributes, args_dict
                )

        return open_span

    if extract_args:  # i.e. extract_args should be an iterable of argument names
        sig = inspect.signature(func)

        if isinstance(extract_args, str):
            extract_args = [extract_args]

        extract_args_final = uniquify_sequence(list(extract_args))
        missing = set(extract_args_final) - set(sig.parameters)
        if missing:
            extract_args_final = [arg for arg in extract_args_final if arg not in missing]
            warnings.warn(
                f'Ignoring missing arguments to extract: {", ".join(sorted(missing))}',
                stacklevel=3,
            )

        if extract_args_final:  # check that there are still arguments to extract

            def open_span(*func_args: P.args, **func_kwargs: P.kwargs):
                args_dict = sig.bind(*func_args, **func_kwargs).arguments

                # This line is the only difference from the extract_args=True case
                args_dict = {k: args_dict[k] for k in extract_args_final}

                return logfire._instrument_span_with_args(  # type: ignore
                    final_span_name, attributes, args_dict
                )

    return open_span


def get_attributes(
    func: Any, msg_template: str | None, tags: Sequence[str] | None
) -> dict[str, otel_types.AttributeValue]:
    func = inspect.unwrap(func)
    if not inspect.isfunction(func) and hasattr(func, '__call__'):
        func = func.__call__
        func = inspect.unwrap(func)
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

    if tags:
        attributes[ATTRIBUTES_TAGS_KEY] = uniquify_sequence(tags)

    return attributes
