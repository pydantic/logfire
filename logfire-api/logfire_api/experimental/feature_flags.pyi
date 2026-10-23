from collections.abc import Mapping
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from enum import Enum
from logfire import Logfire
from pydantic import BaseModel
from typing import Literal, Any, Generic, TypeVar, overload
from typing_extensions import TypeForm

__all__ = ['Flag', 'FlagErrorCode', 'FlagEvaluationDetails', 'FlagEvaluationReason', 'feature_context', 'flag']

InferableFlagValue = bool | str | int | float | Enum | BaseModel
T = TypeVar('T')
InferableFlagT = TypeVar('InferableFlagT', bound=InferableFlagValue)
FlagEvaluationReason = Literal['cached', 'context_override', 'default', 'disabled', 'error', 'split', 'stale', 'static', 'targeting_match', 'unknown']
FlagErrorCode = Literal['flag_not_found', 'general', 'invalid_context', 'parse_error', 'provider_fatal', 'provider_not_ready', 'targeting_key_missing', 'type_mismatch']

@dataclass(frozen=True, slots=True)
class FlagEvaluationDetails(Generic[T]):
    '''The result of evaluating a Logfire feature flag.

    The fields follow OpenFeature\'s evaluation details.

    Use the details as a context manager to tag telemetry with the selected variant. Inside the
    block, Logfire sets the `logfire.variables.<flag name>` baggage entry, the same entry that
    `logfire.var(...).get()` sets. Spans and logs created in the block carry it as an attribute,
    so you can filter them by variant without joining on the trace ID:

    ```python skip="true"
    with new_checkout.details(user_id) as details:
        if details.value:
            ...
    ```

    Baggage also travels to downstream services and to outgoing HTTP requests, including
    requests to third-party APIs. Do not use this for variant names that must stay private.
    '''
    flag_key: str
    value: T
    variant: str | None = ...
    reason: FlagEvaluationReason = ...
    error_code: FlagErrorCode | None = ...
    error_message: str | None = ...
    flag_metadata: Mapping[str, Any] = field(default_factory=dict[str, Any])
    def __enter__(self) -> FlagEvaluationDetails[T]: ...
    def __exit__(self, *exc_info: Any) -> None: ...

class Flag(Generic[T]):
    """A typed feature flag with a safe code default.

    Values are validated with Pydantic before they are returned. Parameterized containers and
    nullable types need an explicit ``type=`` because Python cannot recover their element type from
    a runtime default such as ``[]`` or ``None``.
    """
    @overload
    def __init__(self: Flag[InferableFlagT], name: str, *, default: InferableFlagT, description: str | None = None, logfire_instance: Logfire | None = None) -> None: ...
    @overload
    def __init__(self, name: str, *, type: TypeForm[T], default: T, description: str | None = None, logfire_instance: Logfire | None = None) -> None: ...
    @property
    def name(self) -> str:
        """The stable key used to identify the flag."""
    @property
    def description(self) -> str | None:
        """The optional human-readable description supplied when defining the flag."""
    def value(self, targeting_key: str | None = None, attributes: Mapping[str, Any] | None = None) -> T:
        """Return the flag value for the evaluation context."""
    def details(self, targeting_key: str | None = None, attributes: Mapping[str, Any] | None = None) -> FlagEvaluationDetails[T]:
        """Evaluate the flag and return native Logfire evaluation details."""
    def override(self, value: T) -> AbstractContextManager[None]:
        """Replace the flag value in the current context.

        Use this in tests, or in production to force a value for one request, such as for internal
        users. Evaluations in the block report the `context_override` reason, so overridden values
        stay visible in telemetry.

        The override is stored in a context variable. It applies to async tasks, `asyncio.to_thread`
        and `run_in_executor` calls, and Starlette or FastAPI `TestClient` requests started in the
        block. It does not apply to threads that do not copy the context, such as a plain
        `threading.Thread` or a `concurrent.futures` executor, or to other processes.
        """

@overload
def flag(name: str, *, default: InferableFlagT, description: str | None = None, logfire_instance: Logfire | None = None) -> Flag[InferableFlagT]: ...
@overload
def flag(name: str, *, type: TypeForm[T], default: T, description: str | None = None, logfire_instance: Logfire | None = None) -> Flag[T]: ...
def feature_context(targeting_key: str, *, attributes: Mapping[str, Any] | None = None) -> AbstractContextManager[None]:
    """Set request-local identity and attributes for feature-flag evaluations.

    The targeting key is the evaluation context's OpenFeature targeting key. It must not be empty.
    """
