from collections.abc import Mapping, Sequence
from logfire import Logfire
from openfeature.evaluation_context import EvaluationContext
from openfeature.flag_evaluation import FlagResolutionDetails, FlagValueType
from openfeature.provider import AbstractProvider, Metadata
from typing import TypeVar

__all__ = ['LogfireProvider']

T = TypeVar('T')

class LogfireProvider(AbstractProvider):
    """OpenFeature provider backed by flags declared through Logfire.

    Register this provider explicitly with OpenFeature. Constructing a Logfire flag never changes
    OpenFeature's process-global provider registry.
    """
    def __init__(self, logfire_instance: Logfire | None = None) -> None: ...
    def get_metadata(self) -> Metadata:
        """Return the provider metadata exposed through OpenFeature."""
    def resolve_boolean_details(self, flag_key: str, default_value: bool, evaluation_context: EvaluationContext | None = None) -> FlagResolutionDetails[bool]:
        """Resolve a boolean flag."""
    def resolve_string_details(self, flag_key: str, default_value: str, evaluation_context: EvaluationContext | None = None) -> FlagResolutionDetails[str]:
        """Resolve a string flag."""
    def resolve_integer_details(self, flag_key: str, default_value: int, evaluation_context: EvaluationContext | None = None) -> FlagResolutionDetails[int]:
        """Resolve an integer flag."""
    def resolve_float_details(self, flag_key: str, default_value: float, evaluation_context: EvaluationContext | None = None) -> FlagResolutionDetails[float]:
        """Resolve a floating-point flag."""
    def resolve_object_details(self, flag_key: str, default_value: Sequence[FlagValueType] | Mapping[str, FlagValueType], evaluation_context: EvaluationContext | None = None) -> FlagResolutionDetails[Sequence[FlagValueType] | Mapping[str, FlagValueType]]:
        """Resolve an object flag as JSON-compatible data."""
