from __future__ import annotations as _annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import Any, Generic, Literal, TypeVar

T = TypeVar('T')
T_co = TypeVar('T_co', covariant=True)


@dataclass(kw_only=True)
class VariableResolutionDetails(Generic[T_co]):
    value: T_co
    variant: str | None = None
    exception: Exception | None = None
    _reason: Literal['resolved', 'context_override', 'missing_config', 'unrecognized_variable', 'validation_error', 'other_error']

    def with_value(self, v: T) -> VariableResolutionDetails[T]:
        return replace(self, value=v)


class VariableProvider(ABC):
    @abstractmethod
    def get_serialized_value(
        self,
        variable_name: str,
        targeting_key: str | None = None,
        attributes: Mapping[str, Any] | None = None,
    ) -> VariableResolutionDetails[str | None]:
        raise NotImplementedError


class NoOpProvider(VariableProvider):
    def get_serialized_value(
        self,
        variable_name: str,
        targeting_key: str | None = None,
        attributes: Mapping[str, Any] | None = None,
    ) -> VariableResolutionDetails[str | None]:
        return VariableResolutionDetails(value=None, _reason='resolved')
