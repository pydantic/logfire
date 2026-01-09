# pyright: reportUnusedImport=false
# ruff: noqa: F401
from importlib.util import find_spec
from typing import TYPE_CHECKING

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
    if find_spec('pydantic'):
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
            Variant,
        )
        from logfire.variables.local import LocalVariableProvider
        from logfire.variables.remote import LogfireRemoteVariableProvider
        from logfire.variables.variable import ResolveFunction, Variable, targeting_context

__all__ = [
    'KeyIsNotPresent',
    'KeyIsPresent',
    'LocalVariableProvider',
    'LogfireRemoteVariableProvider',
    'NoOpVariableProvider',
    'RemoteVariablesConfig',
    'ResolveFunction',
    'ResolvedVariable',
    'Rollout',
    'RolloutOverride',
    'SyncMode',
    'ValidationReport',
    'ValueDoesNotEqual',
    'ValueDoesNotMatchRegex',
    'ValueEquals',
    'ValueIsIn',
    'ValueIsNotIn',
    'ValueMatchesRegex',
    'Variable',
    'VariableAlreadyExistsError',
    'VariableConfig',
    'VariableNotFoundError',
    'VariableProvider',
    'VariablesConfig',
    'VariableWriteError',
    'Variant',
    'targeting_context',
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
        Variant,
    )
    from logfire.variables.local import LocalVariableProvider
    from logfire.variables.remote import LogfireRemoteVariableProvider
    from logfire.variables.variable import ResolveFunction, Variable, targeting_context

    return locals()[name]
