from __future__ import annotations

import contextlib
import functools
import inspect
import threading
import warnings
from collections.abc import Callable, Iterable, Sequence
from contextlib import AbstractContextManager, asynccontextmanager, contextmanager
from typing import TYPE_CHECKING, Any, TypeVar

from opentelemetry import trace
from opentelemetry.util import types as otel_types
from typing_extensions import LiteralString, ParamSpec

from ..types import InstrumentMessageTemplateHelper
from .constants import (
    ATTRIBUTES_LOG_LEVEL_NUM_KEY,
    ATTRIBUTES_MESSAGE_TEMPLATE_KEY,
    ATTRIBUTES_TAGS_KEY,
    LevelName,
    log_level_attributes,
)
from .stack_info import get_filepath_attribute
from .utils import handle_internal_errors, uniquify_sequence

if TYPE_CHECKING:
    from .main import Logfire


P = ParamSpec('P')
R = TypeVar('R')
_PreparedExtractArgs = tuple[inspect.Signature, Sequence[str] | None] | None


class _InstrumentInitializationLock:
    def __init__(self) -> None:
        self._lock = threading.RLock()

    def __enter__(self) -> None:
        self._lock.acquire()

    def __exit__(self, *_args: Any) -> None:
        self._lock.release()

    def __getstate__(self) -> dict[str, Any]:
        return {}

    def __setstate__(self, _state: dict[str, Any]) -> None:
        self.__init__()


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
    record_return: bool,
    allow_generator: bool,
    new_trace: bool,
    level: LevelName | int | None = None,
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    from .main import set_user_attributes_on_raw_span

    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        if getattr(func, '__code__', None) in (CONTEXTMANAGER_HELPER_CODE, ASYNCCONTEXTMANAGER_HELPER_CODE):
            warnings.warn(
                '@logfire.instrument should be underneath @contextlib.[async]contextmanager so that it is applied first.',
                stacklevel=2,
            )

        prepared_extract_args = _prepare_extract_args(func, extract_args)
        if msg_template:
            attributes = get_attributes(func, msg_template, tags, InstrumentMessageTemplateHelper.default_template)
            open_span = get_open_span(
                logfire, attributes, span_name, prepared_extract_args, func, new_trace, level=level
            )
        else:
            cached_open_span: Callable[P, AbstractContextManager[Any]] | None = None
            initialization_lock = _InstrumentInitializationLock()

            def get_logfire():
                # Avoid capturing the global instance, which would make the instrumented function
                # unpicklable with cloudpickle.
                from logfire import DEFAULT_LOGFIRE_INSTANCE

                return DEFAULT_LOGFIRE_INSTANCE

            if get_logfire() != logfire:

                def get_logfire():
                    return logfire

            def open_span(*func_args: P.args, **func_kwargs: P.kwargs) -> AbstractContextManager[Any]:
                nonlocal cached_open_span
                if cached_open_span is None:
                    with initialization_lock:
                        if cached_open_span is None:
                            current_logfire = get_logfire()
                            attributes = get_attributes(
                                func,
                                msg_template,
                                tags,
                                current_logfire.config.advanced.instrument_default_msg_template,
                            )
                            cached_open_span = get_open_span(
                                current_logfire,
                                attributes,
                                span_name,
                                prepared_extract_args,
                                func,
                                new_trace,
                                level=level,
                            )
                return cached_open_span(*func_args, **func_kwargs)

        if inspect.isgeneratorfunction(func):
            if not allow_generator:
                warnings.warn(GENERATOR_WARNING_MESSAGE, stacklevel=2)

            def wrapper(*func_args: P.args, **func_kwargs: P.kwargs):  # pyright: ignore[reportUnknownParameterType, reportRedeclaration]
                with open_span(*func_args, **func_kwargs):
                    yield from func(*func_args, **func_kwargs)
        elif inspect.isasyncgenfunction(func):
            if not allow_generator:
                warnings.warn(GENERATOR_WARNING_MESSAGE, stacklevel=2)

            async def wrapper(*func_args: P.args, **func_kwargs: P.kwargs):  # pyright: ignore[reportRedeclaration]
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

            async def wrapper(*func_args: P.args, **func_kwargs: P.kwargs) -> R:  # pyright: ignore[reportRedeclaration]
                with open_span(*func_args, **func_kwargs) as span:
                    result = await func(*func_args, **func_kwargs)
                    if record_return:
                        # open_span returns a FastLogfireSpan, so we can't use span.set_attribute for complex types.
                        # This isn't great because it has to parse the JSON schema.
                        # Not sure if making get_open_span return a LogfireSpan when record_return is True
                        # would be faster overall or if it would be worth the added complexity.
                        set_user_attributes_on_raw_span(span._span, {'return': result})
                    return result
        else:
            # Same as the above, but without the async/await
            def wrapper(*func_args: P.args, **func_kwargs: P.kwargs) -> R:
                with open_span(*func_args, **func_kwargs) as span:
                    result = func(*func_args, **func_kwargs)
                    if record_return:
                        set_user_attributes_on_raw_span(span._span, {'return': result})
                    return result

        wrapper = functools.wraps(func)(wrapper)  # pyright: ignore[reportUnknownVariableType, reportAssignmentType]
        return wrapper

    return decorator


def get_open_span(
    logfire: Logfire,
    attributes: dict[str, otel_types.AttributeValue],
    span_name: str | None,
    extract_args: _PreparedExtractArgs,
    func: Callable[P, R],
    new_trace: bool,
    level: LevelName | int | None = None,
) -> Callable[P, AbstractContextManager[Any]]:
    from .main import NoopSpan

    final_span_name: str = span_name or attributes[ATTRIBUTES_MESSAGE_TEMPLATE_KEY]  # pyright: ignore[reportAssignmentType]

    level_num: int | None = None
    if level is not None:
        level_attrs = log_level_attributes(level)
        level_num = int(level_attrs[ATTRIBUTES_LOG_LEVEL_NUM_KEY])
        attributes = {**attributes, **level_attrs}

    def get_logfire():
        # This avoids having a `logfire` closure variable, which would make the instrumented
        # function unpicklable with cloudpickle.
        # This is only possible when using `logfire.instrument` on the global instance, i.e. on the module,
        # but that's the common case.
        from logfire import DEFAULT_LOGFIRE_INSTANCE

        return DEFAULT_LOGFIRE_INSTANCE

    if get_logfire() != logfire:

        def get_logfire():
            return logfire

    if new_trace:

        def extra_span_kwargs() -> dict[str, Any]:
            prev_context = trace.get_current_span().get_span_context()
            if not prev_context.is_valid:
                return {}
            return {
                'links': [trace.Link(prev_context)],
                'context': trace.set_span_in_context(trace.INVALID_SPAN),
            }
    else:

        def extra_span_kwargs() -> dict[str, Any]:
            return {}

    # This is the fast case for when there are no arguments to extract
    def open_span(*_: P.args, **__: P.kwargs):  # pyright: ignore[reportRedeclaration]
        if level_num is not None and level_num < get_logfire().config.min_level:
            return NoopSpan()
        return get_logfire()._fast_span(final_span_name, attributes, **extra_span_kwargs())  # pyright: ignore[reportPrivateUsage]

    if extract_args:
        sig, extract_args_final = extract_args

        def open_span(*func_args: P.args, **func_kwargs: P.kwargs):
            if level_num is not None and level_num < get_logfire().config.min_level:
                return NoopSpan()
            bound = sig.bind(*func_args, **func_kwargs)
            bound.apply_defaults()
            args_dict = bound.arguments
            if extract_args_final is not None:
                args_dict = {key: args_dict[key] for key in extract_args_final}

            return get_logfire()._instrument_span_with_args(  # pyright: ignore[reportPrivateUsage]
                final_span_name, attributes, args_dict, **extra_span_kwargs()
            )

    return open_span


def _prepare_extract_args(func: Callable[..., Any], extract_args: bool | Iterable[str]) -> _PreparedExtractArgs:
    if extract_args is True:
        sig = inspect.signature(func)
        if sig.parameters:
            return sig, None
    elif extract_args:
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
        if extract_args_final:
            return sig, extract_args_final
    return None


def get_attributes(
    func: Any,
    msg_template: str | None,
    tags: Sequence[str] | None,
    default_msg_template: Callable[[InstrumentMessageTemplateHelper], str],
) -> dict[str, otel_types.AttributeValue]:
    helper = InstrumentMessageTemplateHelper(func)
    func = helper.callable
    func_name = helper.qualname
    if not msg_template:
        with handle_internal_errors:
            msg_template = default_msg_template(helper)
        if not msg_template:
            msg_template = helper.default_template()
    attributes: dict[str, otel_types.AttributeValue] = {
        'code.function': func_name,
        ATTRIBUTES_MESSAGE_TEMPLATE_KEY: msg_template,
    }
    with contextlib.suppress(Exception):
        attributes['code.lineno'] = func.__code__.co_firstlineno
    with contextlib.suppress(Exception):
        attributes.update(get_filepath_attribute(inspect.getsourcefile(func)))  # pyright: ignore[reportCallIssue, reportArgumentType]

    if tags:
        attributes[ATTRIBUTES_TAGS_KEY] = uniquify_sequence(tags)

    return attributes
