from __future__ import annotations as _annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from typing import Any, TypeVar

from logfire.variables.variable import VariableResolutionDetails

T = TypeVar('T')
T_co = TypeVar('T_co', covariant=True)


class VariableProvider(ABC):
    @abstractmethod
    def get_serialized_value(
        self,
        variable_name: str,
        targeting_key: str | None = None,
        attributes: Mapping[str, Any] | None = None,
    ) -> VariableResolutionDetails[str | None]:
        raise NotImplementedError

    def shutdown(self):
        pass


class NoOpVariableProvider(VariableProvider):
    def get_serialized_value(
        self,
        variable_name: str,
        targeting_key: str | None = None,
        attributes: Mapping[str, Any] | None = None,
    ) -> VariableResolutionDetails[str | None]:
        return VariableResolutionDetails(value=None, _reason='resolved')
