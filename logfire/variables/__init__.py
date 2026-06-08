# pyright: reportUnusedImport=false
# ruff: noqa: F401
from __future__ import annotations as _annotations

from importlib.util import find_spec
from typing import TYPE_CHECKING

from logfire.variables.abstract import (
    ResolutionReason,
    ResolvedVariable,
    SyncMode,
    ValidationReport,
    VariableAlreadyExistsError,
    VariableNotFoundError,
    VariableWriteError,
)
from logfire.variables.composition import (
    ComposedReference,
    VariableCompositionCycleError,
    VariableCompositionError,
)

if TYPE_CHECKING:
    # We use a TYPE_CHECKING block here because we need to do these imports lazily to prevent issues due to loading the
    # logfire pydantic plugin.
    # If you change the imports here, you need to update the __getattr__ definition below to match.
    from logfire.variables.config import (
        KeyIsNotPresent,
        KeyIsPresent,
        LabeledValue,
        LabelRef,
        LatestVersion,
        LocalVariablesOptions,
        Rollout,
        RolloutOverride,
        TemplateMismatchPolicy,
        ValueDoesNotEqual,
        ValueDoesNotMatchRegex,
        ValueEquals,
        ValueIsIn,
        ValueIsNotIn,
        ValueMatchesRegex,
        VariableConfig,
        VariablesConfig,
        VariableTypeConfig,
    )
    from logfire.variables.variable import (
        ResolveFunction,
        TemplateInputsMismatchError,
        TemplateVariable,
        Variable,
        targeting_context,
    )

__all__ = [
    # Variable classes
    'Variable',
    'TemplateVariable',
    'ResolvedVariable',
    'ResolveFunction',
    # Configuration classes
    'VariablesConfig',
    'VariableConfig',
    'VariableTypeConfig',
    'LocalVariablesOptions',
    # Label and rollout configuration
    'LabeledValue',
    'LabelRef',
    'LatestVersion',
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
    # Context managers and utilities
    'targeting_context',
    # Types
    'ComposedReference',
    'ResolutionReason',
    'SyncMode',
    'TemplateMismatchPolicy',
    'ValidationReport',
    # Exceptions
    'TemplateInputsMismatchError',
    'VariableAlreadyExistsError',
    'VariableCompositionCycleError',
    'VariableCompositionError',
    'VariableNotFoundError',
    'VariableWriteError',
]


def ensure_variables_dependencies() -> None:
    """Raise a clear `ImportError` if a package required to use managed variables is missing.

    Using managed variables — declaring a `var()`/`template_var()`, or touching the public
    config classes — needs the `logfire[variables]` extra. This is checked eagerly at those
    entry points (rather than lazily mid-resolution) so a missing dependency surfaces as an
    actionable error instead of, e.g., a composition value silently falling back to its code
    default. Plain `import logfire` and the rest of the SDK keep working without the extra, so
    this must only run on *use*, never at module-import time.
    """
    # Keep this in sync with the `variables` optional-dependency group in pyproject.toml. Each
    # entry is (import module name, pip distribution name) — they differ for pydantic-handlebars.
    for module_name, distribution_name in (('pydantic', 'pydantic'), ('pydantic_handlebars', 'pydantic-handlebars')):
        if not find_spec(module_name):  # pragma: no cover
            raise ImportError(
                f'Using managed variables requires the `{distribution_name}` package.\n'
                'You can install this with:\n'
                "    pip install 'logfire[variables]'"
            )


def __getattr__(name: str):
    if name not in __all__:
        raise AttributeError(f'module {__name__!r} has no attribute {name!r}')

    ensure_variables_dependencies()

    from logfire.variables.config import (
        KeyIsNotPresent,
        KeyIsPresent,
        LabeledValue,
        LabelRef,
        LatestVersion,
        LocalVariablesOptions,
        Rollout,
        RolloutOverride,
        TemplateMismatchPolicy,
        ValueDoesNotEqual,
        ValueDoesNotMatchRegex,
        ValueEquals,
        ValueIsIn,
        ValueIsNotIn,
        ValueMatchesRegex,
        VariableConfig,
        VariablesConfig,
        VariableTypeConfig,
    )
    from logfire.variables.variable import (
        ResolveFunction,
        TemplateInputsMismatchError,
        TemplateVariable,
        Variable,
        targeting_context,
    )

    return locals()[name]
