# pyright: reportUnusedImport=false
# ruff: noqa: F401
from __future__ import annotations as _annotations

from collections.abc import Sequence
from importlib.util import find_spec
from typing import TYPE_CHECKING, Any

from logfire.variables.abstract import (
    NoOpVariableProvider,
    ResolvedVariable,
    SyncMode,
    ValidationReport,
    VariableAlreadyExistsError,
    VariableNotFoundError,
    VariableProvider,
    VariableWriteError,
)

if TYPE_CHECKING:
    # We use a TYPE_CHECKING block here because we need to do these imports lazily to prevent issues due to loading the
    # logfire pydantic plugin.
    # If you change the imports here, you need to update the __getattr__ definition below to match.
    from logfire.variables.config import (
        KeyIsNotPresent,
        KeyIsPresent,
        RemoteVariablesConfig,
        Rollout,
        RolloutOverride,
        ValueDoesNotEqual,
        ValueDoesNotMatchRegex,
        ValueEquals,
        ValueIsIn,
        ValueIsNotIn,
        ValueMatchesRegex,
        VariableConfig,
        VariablesConfig,
        VariableTypeConfig,
        Variant,
    )
    from logfire.variables.local import LocalVariableProvider
    from logfire.variables.remote import LogfireRemoteVariableProvider
    from logfire.variables.variable import (
        ResolveFunction,
        Variable,
        override_variables,
        targeting_context,
    )

__all__ = [
    # Module-level convenience functions
    'get',
    'push',
    'push_types',
    'push_variable_types',
    'validate',
    'push_config',
    'pull_config',
    'build_config',
    # Variable classes
    'Variable',
    'ResolvedVariable',
    'ResolveFunction',
    # Configuration classes
    'VariablesConfig',
    'VariableConfig',
    'VariableTypeConfig',
    'RemoteVariablesConfig',
    # Variant and rollout configuration
    'Variant',
    'Rollout',
    'RolloutOverride',
    # Targeting conditions
    'KeyIsPresent',
    'KeyIsNotPresent',
    'ValueEquals',
    'ValueDoesNotEqual',
    'ValueIsIn',
    'ValueIsNotIn',
    'ValueMatchesRegex',
    'ValueDoesNotMatchRegex',
    # Providers
    'VariableProvider',
    'LocalVariableProvider',
    'LogfireRemoteVariableProvider',
    'NoOpVariableProvider',
    # Context managers and utilities
    'override_variables',
    'targeting_context',
    # Types
    'SyncMode',
    'ValidationReport',
    # Exceptions
    'VariableAlreadyExistsError',
    'VariableNotFoundError',
    'VariableWriteError',
]


def __getattr__(name: str):
    if name not in __all__:
        raise AttributeError(f'module {__name__!r} has no attribute {name!r}')

    if not find_spec('pydantic'):  # pragma: no cover
        raise ImportError(
            'Using managed variables requires the `pydantic` package.\n'
            'You can install this with:\n'
            "    pip install 'logfire[variables]'"
        )

    from logfire.variables.config import (
        KeyIsNotPresent,
        KeyIsPresent,
        RemoteVariablesConfig,
        Rollout,
        RolloutOverride,
        ValueDoesNotEqual,
        ValueDoesNotMatchRegex,
        ValueEquals,
        ValueIsIn,
        ValueIsNotIn,
        ValueMatchesRegex,
        VariableConfig,
        VariablesConfig,
        VariableTypeConfig,
        Variant,
    )
    from logfire.variables.local import LocalVariableProvider
    from logfire.variables.remote import LogfireRemoteVariableProvider
    from logfire.variables.variable import (
        ResolveFunction,
        Variable,
        override_variables,
        targeting_context,
    )

    return locals()[name]


def _require_pydantic() -> None:
    if not find_spec('pydantic'):  # pragma: no cover
        raise ImportError(
            'Using managed variables requires the `pydantic` package.\n'
            'You can install this with:\n'
            "    pip install 'logfire[variables]'"
        )


def _default_logfire():
    import logfire

    return logfire.DEFAULT_LOGFIRE_INSTANCE


def get():
    """Return all variables registered on the default Logfire instance."""
    _require_pydantic()
    return _default_logfire().get_variables()


def push(
    variables: list[Variable[Any]] | None = None, *, dry_run: bool = False, yes: bool = False, strict: bool = False
) -> bool:
    """Push variable definitions using the default Logfire instance."""
    _require_pydantic()
    return _default_logfire().push_variables(variables, dry_run=dry_run, yes=yes, strict=strict)


def push_types(types: Sequence[type[Any] | tuple[type[Any], str]], *, dry_run: bool = False, yes: bool = False) -> bool:
    """Push variable type definitions using the default Logfire instance."""
    _require_pydantic()
    return _default_logfire().push_variable_types(types, dry_run=dry_run, yes=yes)


def push_variable_types(
    types: Sequence[type[Any] | tuple[type[Any], str]], *, dry_run: bool = False, yes: bool = False
) -> bool:
    """Alias for push_types."""
    return push_types(types, dry_run=dry_run, yes=yes)


def validate(variables: list[Variable[Any]] | None = None) -> ValidationReport:
    """Validate variable definitions using the default Logfire instance."""
    _require_pydantic()
    return _default_logfire().validate_variables(variables)


def push_config(config: VariablesConfig, *, mode: SyncMode = 'merge', dry_run: bool = False, yes: bool = False) -> bool:
    """Sync variable config using the default Logfire instance."""
    _require_pydantic()
    return _default_logfire().push_config(config, mode=mode, dry_run=dry_run, yes=yes)


def pull_config():
    """Pull variable config using the default Logfire instance."""
    _require_pydantic()
    return _default_logfire().pull_config()


def build_config():
    """Build variable config using the default Logfire instance."""
    _require_pydantic()
    return _default_logfire().build_config()
