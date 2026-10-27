"""Experimental code-first feature flags backed by Logfire managed variables.

This API may change while its evaluation context and telemetry contracts are refined.
"""

from __future__ import annotations

from collections.abc import Mapping
from contextlib import AbstractContextManager, ExitStack
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any, Generic, Literal, TypeVar, overload

from typing_extensions import TypeForm

from logfire.variables import ensure_variables_dependencies

if TYPE_CHECKING:
    from pydantic import BaseModel

    from logfire import Logfire
    from logfire.variables.variable import _ManagedVariableFlagAdapter  # pyright: ignore[reportPrivateUsage]

    InferableFlagValue = bool | str | int | float | Enum | BaseModel
else:
    InferableFlagValue = Any

__all__ = (
    'Flag',
    'FlagErrorCode',
    'FlagEvaluationDetails',
    'FlagEvaluationReason',
    'feature_context',
    'flag',
)


T = TypeVar('T')
InferableFlagT = TypeVar('InferableFlagT', bound=InferableFlagValue)

FlagEvaluationReason = Literal[
    'cached',
    'context_override',
    'default',
    'disabled',
    'error',
    'split',
    'stale',
    'static',
    'targeting_match',
    'unknown',
]
"""Why a feature-flag evaluation returned its value.

The values follow the OpenFeature specification's resolution reasons, lowercased, plus the
Logfire-specific `context_override`:

- `static`: the configured rollout serves one value to every subject.
- `split`: a percentage rollout selected the value.
- `targeting_match`: a targeting rule matched the evaluation context.
- `default`: the code default was used because no configured value applies.
- `stale`: the value comes from configuration that a recent refresh could not update.
- `error`: evaluation failed and returned the code default. `error_code` says why.
- `context_override`: a value set with `Flag.override()` was used. Managed variables report the
  same reason.
- `cached`, `disabled`, `unknown`: reserved to match OpenFeature. Logfire does not return them.
"""

FlagErrorCode = Literal[
    'flag_not_found',
    'general',
    'invalid_context',
    'parse_error',
    'provider_fatal',
    'provider_not_ready',
    'targeting_key_missing',
    'type_mismatch',
]
"""A stable classification for a feature-flag evaluation error.

The values follow the OpenFeature specification's error codes, lowercased. `targeting_key_missing`
and `invalid_context` are reserved to match OpenFeature. Logfire does not return them: an evaluation
without a targeting key uses a random fallback key, which stays the same for the current request,
or outside a trace for the current async task or thread.
"""


@dataclass(frozen=True, slots=True)
class FlagEvaluationDetails(Generic[T]):
    """The result of evaluating a Logfire feature flag.

    The fields follow OpenFeature's evaluation details.

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
    """

    flag_key: str
    value: T
    variant: str | None = None
    reason: FlagEvaluationReason = 'default'
    error_code: FlagErrorCode | None = None
    error_message: str | None = None
    flag_metadata: Mapping[str, Any] = field(default_factory=dict[str, Any])
    _baggage_scopes: list[ExitStack] = field(
        default_factory=list[ExitStack], init=False, repr=False, compare=False, hash=False
    )

    def __enter__(self) -> FlagEvaluationDetails[T]:
        import logfire

        if self.variant is not None:
            label = self.variant
        elif self.reason == 'context_override':
            label = '<context_override>'
        else:
            label = '<code_default>'
        baggage_entries = {f'logfire.variables.{self.flag_key}': label}
        version = self.flag_metadata.get('logfire.value_version')
        if version is not None:
            baggage_entries[f'logfire.variables.{self.flag_key}.version'] = str(version)
        stack = ExitStack()
        stack.enter_context(logfire.set_baggage(**baggage_entries))
        # One stack per entry, so nested or repeated use of the same details unwinds in order.
        self._baggage_scopes.append(stack)
        return self

    def __exit__(self, *exc_info: Any) -> None:
        self._baggage_scopes.pop().close()


class Flag(Generic[T]):
    """A typed feature flag with a safe code default.

    Values are validated with Pydantic before they are returned. Parameterized containers and
    nullable types need an explicit ``type=`` because Python cannot recover their element type from
    a runtime default such as ``[]`` or ``None``.
    """

    __slots__ = ('_adapter',)

    @overload
    def __init__(
        self: Flag[InferableFlagT],
        name: str,
        *,
        default: InferableFlagT,
        description: str | None = None,
        logfire_instance: Logfire | None = None,
    ) -> None: ...

    @overload
    def __init__(
        self,
        name: str,
        *,
        type: TypeForm[T],
        default: T,
        description: str | None = None,
        logfire_instance: Logfire | None = None,
    ) -> None: ...

    def __init__(
        self,
        name: str,
        *,
        default: T,
        type: Any | None = None,
        description: str | None = None,
        logfire_instance: Logfire | None = None,
    ):
        """Define a typed feature flag backed by the configured Logfire provider."""
        ensure_variables_dependencies('feature-flags')
        if logfire_instance is None:
            from logfire import DEFAULT_LOGFIRE_INSTANCE

            logfire_instance = DEFAULT_LOGFIRE_INSTANCE
        logfire_instance._validate_variable_registration(name)  # pyright: ignore[reportPrivateUsage]
        if type is None:
            type = _infer_flag_type(default)
        self._adapter: _ManagedVariableFlagAdapter[T] = logfire_instance._flag(  # pyright: ignore[reportPrivateUsage]
            name, type=type, default=default, description=description
        )

    @property
    def name(self) -> str:
        """The stable key used to identify the flag."""
        return self._adapter.name

    @property
    def description(self) -> str | None:
        """The optional human-readable description supplied when defining the flag."""
        return self._adapter.description

    def value(
        self,
        targeting_key: str | None = None,
        attributes: Mapping[str, Any] | None = None,
    ) -> T:
        """Return the flag value for the evaluation context."""
        return self.details(targeting_key, attributes).value

    def details(
        self,
        targeting_key: str | None = None,
        attributes: Mapping[str, Any] | None = None,
    ) -> FlagEvaluationDetails[T]:
        """Evaluate the flag and return native Logfire evaluation details."""
        return self._adapter.evaluate_flag(targeting_key, attributes)

    def override(self, value: T) -> AbstractContextManager[None]:
        """Replace the flag value in the current context.

        Use this in tests, or in production to force a value for one request, such as for internal
        users. Evaluations in the block report the `context_override` reason, so overridden values
        stay visible in telemetry.

        The override is stored in a context variable. It applies to async tasks, `asyncio.to_thread`
        calls, and Starlette or FastAPI `TestClient` requests started in the block. After
        `logfire.configure()`, it also applies to thread pool tasks, including `loop.run_in_executor`.
        It does not apply to a plain `threading.Thread` or to other processes.
        """
        return self._adapter.override(value)


def _infer_flag_type(default: object) -> type[Any]:
    if default is None or isinstance(default, (list, dict, set, tuple)):
        message = 'Pass type=... for nullable or parameterized feature flags; their type cannot be inferred safely.'
        raise TypeError(message)
    return type(default)


@overload
def flag(
    name: str,
    *,
    default: InferableFlagT,
    description: str | None = None,
    logfire_instance: Logfire | None = None,
) -> Flag[InferableFlagT]: ...


@overload
def flag(
    name: str,
    *,
    type: TypeForm[T],
    default: T,
    description: str | None = None,
    logfire_instance: Logfire | None = None,
) -> Flag[T]: ...


def flag(
    name: str,
    *,
    default: T,
    type: Any = None,
    description: str | None = None,
    logfire_instance: Logfire | None = None,
) -> Flag[T]:
    """Define a Pydantic-validated feature flag with a safe code default."""
    return Flag(name, type=type, default=default, description=description, logfire_instance=logfire_instance)


def feature_context(
    targeting_key: str,
    *,
    attributes: Mapping[str, Any] | None = None,
) -> AbstractContextManager[None]:
    """Set request-local identity and attributes for feature-flag evaluations.

    The targeting key is the evaluation context's OpenFeature targeting key. It must not be empty.
    """
    ensure_variables_dependencies('feature-flags')
    from logfire.variables.variable import feature_context as _feature_context

    return _feature_context(targeting_key, attributes=attributes)
