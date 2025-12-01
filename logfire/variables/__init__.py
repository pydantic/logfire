from importlib.util import find_spec

from logfire.variables.abstract import NoOpVariableProvider, VariableProvider, VariableResolutionDetails

if find_spec('pydantic'):
    from logfire.variables.config import (
        KeyIsNotPresent,
        KeyIsPresent,
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
    from logfire.variables.variable import Variable

__all__ = [
    'KeyIsNotPresent',
    'KeyIsPresent',
    'LocalVariableProvider',
    'LogfireRemoteVariableProvider',
    'NoOpVariableProvider',
    'Rollout',
    'RolloutOverride',
    'ValueDoesNotEqual',
    'ValueDoesNotMatchRegex',
    'ValueEquals',
    'ValueIsIn',
    'ValueIsNotIn',
    'ValueMatchesRegex',
    'Variable',
    'VariableConfig',
    'VariableProvider',
    'VariableResolutionDetails',
    'VariablesConfig',
    'Variant',
]


def __getattr__(name: str):
    if name in __all__:
        raise ImportError(
            'Using managed variables requires the `pydantic` package.\n'
            'You can install this with:\n'
            "    pip install 'logfire[variables]'"
        )

    raise AttributeError(f'module {__name__!r} has no attribute {name!r}')
