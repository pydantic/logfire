from __future__ import annotations as _annotations

import inspect
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any, Generic, Literal, Protocol, TypeVar

from pydantic import TypeAdapter, ValidationError
from typing_extensions import TypeIs

import logfire

if TYPE_CHECKING:
    from logfire import Logfire

T = TypeVar('T')
T_co = TypeVar('T_co', covariant=True)


_VARIABLE_OVERRIDES = ContextVar[dict[str, Any] | None]('_VARIABLE_OVERRIDES', default=None)

_DEFAULT_SENTINEL = object()


@dataclass(kw_only=True)
class VariableResolutionDetails(Generic[T_co]):
    value: T_co
    variant: str | None = None
    exception: Exception | None = None
    _reason: Literal[
        'resolved', 'context_override', 'missing_config', 'unrecognized_variable', 'validation_error', 'other_error'
    ]

    def with_value(self, v: T) -> VariableResolutionDetails[T]:
        return replace(self, value=v)  # pyright: ignore[reportReturnType]


class ResolveFunction(Protocol[T_co]):
    def __call__(self, targeting_key: str | None, attributes: Mapping[str, Any] | None) -> T_co:
        raise NotImplementedError


def is_resolve_function(f: Any) -> TypeIs[ResolveFunction[Any]]:
    if not callable(f):
        return False
    signature = inspect.signature(f)
    params = list(signature.parameters.values())
    if len(params) == 2 and params[0].name == 'targeting_key' and params[1].name == 'attributes':
        return True
    return False


class Variable(Generic[T]):
    """TODO: Need to add otel instrumentation in some way
      Should the default be that logfire dumps a span with the details into the project for you?
      And there's no in-process otel? But you can enable that?
    TODO: Add get_sync method or similar
    TODO: Need to decide how this is going to work. Options:
    """

    name: str
    default: T | ResolveFunction[T]
    value_type: type[T] | None = None

    logfire_instance: Logfire

    def __init__(
        self,
        name: str,
        *,
        default: T | ResolveFunction[T],
        type: type[T],
        logfire_instance: Logfire,
    ):
        self.name = name
        self.default = default

        self.logfire_instance = logfire_instance
        self.type_adapter = TypeAdapter[T](type)

    @contextmanager
    def override(self, value: T | ResolveFunction[T]) -> Iterator[None]:
        current = _VARIABLE_OVERRIDES.get() or {}
        token = _VARIABLE_OVERRIDES.set({**current, self.name: value})
        try:
            yield
        finally:
            _VARIABLE_OVERRIDES.reset(token)

    async def get(self, targeting_key: str | None = None, attributes: Mapping[str, Any] | None = None) -> T:
        return (await self.get_details(targeting_key, attributes)).value

    async def get_details(
        self, targeting_key: str | None = None, attributes: Mapping[str, Any] | None = None
    ) -> VariableResolutionDetails[T]:
        merged_attributes = self._get_merged_attributes(attributes)

        # TODO: How much of the following code should be in the try: except:?
        try:
            if (context_overrides := _VARIABLE_OVERRIDES.get()) is not None and (
                context_value := context_overrides.get(self.name)
            ) is not None:
                if is_resolve_function(context_value):
                    context_value = context_value(targeting_key, merged_attributes)
                return VariableResolutionDetails(value=context_value, _reason='context_override')

            provider = self.logfire_instance.config.variables.provider
            serialized_result = provider.get_serialized_value(self.name, targeting_key, merged_attributes)

            if serialized_result.value is None:
                default = self._get_default(targeting_key, merged_attributes)
                return serialized_result.with_value(default)

            try:
                value = self.type_adapter.validate_json(serialized_result.value)
            except ValidationError as e:
                default = self._get_default(targeting_key, merged_attributes)
                return VariableResolutionDetails(value=default, exception=e, _reason='validation_error')

            return VariableResolutionDetails(value=value, variant=serialized_result.variant, _reason='resolved')

        except Exception as e:
            default = self._get_default(targeting_key, merged_attributes)
            return VariableResolutionDetails(value=default, exception=e, _reason='other_error')

    def _get_default(self, targeting_key: str | None = None, merged_attributes: Mapping[str, Any] | None = None) -> T:
        if is_resolve_function(self.default):
            return self.default(targeting_key, merged_attributes)
        else:
            return self.default

    def _get_merged_attributes(self, attributes: Mapping[str, Any] | None = None) -> Mapping[str, Any]:
        result = dict(attributes) if attributes else {}
        variables_options = self.logfire_instance.config.variables
        if variables_options.include_baggage_in_context:
            result.update(logfire.get_baggage())
        if variables_options.include_resource_attributes_in_context:
            result.update(self.logfire_instance.resource_attributes)
        return result
