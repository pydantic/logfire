from __future__ import annotations as _annotations

import json
import sys
import warnings
from abc import ABC, abstractmethod
from collections.abc import Mapping
from contextlib import ExitStack
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Generic, Literal, TypeVar

if TYPE_CHECKING:
    from logfire.variables.config import VariableConfig, VariablesConfig
    from logfire.variables.variable import Variable

# ANSI color codes for terminal output
ANSI_RESET = '\033[0m'
ANSI_RED = '\033[31m'
ANSI_GREEN = '\033[32m'
ANSI_YELLOW = '\033[33m'
ANSI_CYAN = '\033[36m'
ANSI_GRAY = '\033[90m'

__all__ = (
    'ResolvedVariable',
    'VariableProvider',
    'NoOpVariableProvider',
    'VariableWriteError',
    'VariableNotFoundError',
    'VariableAlreadyExistsError',
)

T = TypeVar('T')
T_co = TypeVar('T_co', covariant=True)

if not TYPE_CHECKING:  # pragma: no branch
    if sys.version_info < (3, 10):
        _dataclass = dataclass

        # TODO: Drop this when we drop support for python 3.9
        # Prevent errors when using kw_only with dataclasses in Python<3.10
        def dataclass(*args, **kwargs):
            kwargs.pop('kw_only', None)
            return _dataclass(*args, **kwargs)


class VariableWriteError(Exception):
    """Base exception for variable write operation failures."""

    pass


class VariableNotFoundError(VariableWriteError):
    """Raised when a variable is not found."""

    pass


class VariableAlreadyExistsError(VariableWriteError):
    """Raised when trying to create a variable that already exists."""

    pass


@dataclass(kw_only=True)
class ResolvedVariable(Generic[T_co]):
    """Details about a variable resolution including value, variant, and any errors.

    This class can be used as a context manager. When used as a context manager, it
    automatically sets baggage with the variable name and variant, enabling downstream
    spans and logs to be associated with the variable resolution that was active at the time.

    Example:
        ```python
        my_var = logfire.var(name='my_var', type=str, default='default')
        with my_var.get() as details:
            # Inside this context, baggage is set with:
            # logfire.variables.my_var = <variant_name> (or '<code_default>' if no variant)
            value = details.value
            # Any spans/logs created here will have the baggage attached
        ```
    """

    name: str
    """The name of the variable."""
    value: T_co
    """The resolved value of the variable."""
    _reason: Literal[
        'resolved',
        'context_override',
        'missing_config',
        'unrecognized_variable',
        'validation_error',
        'other_error',
        'no_provider',
    ]  # we might eventually make this public, but I didn't want to yet
    """Internal field indicating how the value was resolved."""
    # Note: I had to put _reason before fields with defaults for the sake of Python 3.9
    # TODO: Move to the end when we drop support for 3.9
    variant: str | None = None
    """The key of the selected variant, if any."""
    exception: Exception | None = None
    """Any exception that occurred during resolution."""

    def __post_init__(self):
        self._exit_stack = ExitStack()

    def __enter__(self):
        self._exit_stack.__enter__()

        import logfire

        self._exit_stack.enter_context(
            logfire.set_baggage(**{f'logfire.variables.{self.name}': self.variant or '<code_default>'})
        )

        return self

    def __exit__(self, exc_type: type[BaseException] | None, exc_val: BaseException | None, exc_tb: Any) -> None:
        self._exit_stack.__exit__(exc_type, exc_val, exc_tb)


# --- Dataclasses for push/validate operations ---


@dataclass
class VariantCompatibility:
    """Result of checking a variant's compatibility with a schema."""

    variant_key: str
    serialized_value: str
    is_compatible: bool
    error: str | None = None


@dataclass
class VariableChange:
    """Represents a change to be made to a variable."""

    name: str
    change_type: str  # 'create', 'update_schema', 'update_description', 'no_change'
    local_schema: dict[str, Any] | None = None
    server_schema: dict[str, Any] | None = None
    initial_variant_value: str | None = None  # JSON serialized
    incompatible_variants: list[VariantCompatibility] | None = None
    server_id: str | None = None  # For updates
    local_description: str | None = None
    server_description: str | None = None
    description_differs: bool = False  # True if descriptions differ (for warning)


@dataclass
class VariableDiff:
    """Represents the diff between local and server variables."""

    changes: list[VariableChange]
    orphaned_server_variables: list[str]  # Variables on server not in local code

    @property
    def has_changes(self) -> bool:
        """Return True if there are any changes to apply."""
        return any(c.change_type != 'no_change' for c in self.changes)


@dataclass
class VariantValidationError:
    """Represents a validation error for a specific variant."""

    variable_name: str
    variant_key: str | None
    error: Exception


@dataclass
class DescriptionDifference:
    """Represents a description difference between local and server."""

    variable_name: str
    local_description: str | None
    server_description: str | None


@dataclass
class ValidationReport:
    """Report of variable validation results."""

    errors: list[VariantValidationError]
    variables_checked: int
    variables_not_on_server: list[str]
    description_differences: list[DescriptionDifference]

    @property
    def has_errors(self) -> bool:
        """Return True if there are any validation errors."""
        return len(self.errors) > 0 or len(self.variables_not_on_server) > 0


# --- Helper functions for push/validate operations ---


def _get_json_schema(variable: Variable[Any]) -> dict[str, Any]:
    """Get the JSON schema for a variable's type."""
    return variable.type_adapter.json_schema()


def _get_default_serialized(variable: Variable[Any]) -> str | None:
    """Get the serialized default value for a variable.

    Returns None if the default is a ResolveFunction (can't serialize a function).
    """
    from logfire.variables.variable import is_resolve_function

    if is_resolve_function(variable.default):
        return None
    # Serialize the default value using Pydantic
    return variable.type_adapter.dump_json(variable.default).decode('utf-8')


def _check_variant_compatibility(
    variable: Variable[Any],
    variant_key: str,
    serialized_value: str,
) -> VariantCompatibility:
    """Check if a variant's value is compatible with the variable's type."""
    from pydantic import ValidationError

    try:
        variable.type_adapter.validate_json(serialized_value)
        return VariantCompatibility(
            variant_key=variant_key,
            serialized_value=serialized_value,
            is_compatible=True,
        )
    except ValidationError as e:
        return VariantCompatibility(
            variant_key=variant_key,
            serialized_value=serialized_value,
            is_compatible=False,
            error=str(e),
        )


def _compute_diff(
    variables: list[Variable[Any]],
    server_config: VariablesConfig,
) -> VariableDiff:
    """Compute the diff between local variables and server config.

    Args:
        variables: Local variable definitions.
        server_config: Server variable configurations (from provider.get_all_variables_config()).

    Returns:
        A VariableDiff describing the changes needed.
    """
    changes: list[VariableChange] = []
    local_names = {v.name for v in variables}

    for variable in variables:
        local_schema = _get_json_schema(variable)
        local_description = variable.description
        server_var = server_config.variables.get(variable.name)

        if server_var is None:
            # New variable - needs to be created
            default_serialized = _get_default_serialized(variable)
            changes.append(
                VariableChange(
                    name=variable.name,
                    change_type='create',
                    local_schema=local_schema,
                    initial_variant_value=default_serialized,
                    local_description=local_description,
                )
            )
        else:
            # Variable exists - check if schema changed
            server_schema = server_var.json_schema
            server_description = server_var.description

            # Normalize schemas for comparison (remove $defs if empty, etc.)
            local_normalized = json.dumps(local_schema, sort_keys=True)
            server_normalized = json.dumps(server_schema, sort_keys=True) if server_schema else '{}'

            schema_changed = local_normalized != server_normalized

            # Check if description differs (for warning purposes)
            # Normalize: treat None and empty string as equivalent
            local_desc_normalized = local_description or None
            server_desc_normalized = server_description or None
            description_differs = local_desc_normalized != server_desc_normalized

            if schema_changed:
                # Schema changed - check variant compatibility
                incompatible: list[VariantCompatibility] = []
                for variant_key, variant in server_var.variants.items():
                    compat = _check_variant_compatibility(
                        variable,
                        variant_key,
                        variant.serialized_value,
                    )
                    if not compat.is_compatible:
                        incompatible.append(compat)

                changes.append(
                    VariableChange(
                        name=variable.name,
                        change_type='update_schema',
                        local_schema=local_schema,
                        server_schema=server_schema,
                        incompatible_variants=incompatible if incompatible else None,
                        local_description=local_description,
                        server_description=server_description,
                        description_differs=description_differs,
                    )
                )
            else:
                # No schema change needed
                changes.append(
                    VariableChange(
                        name=variable.name,
                        change_type='no_change',
                        local_description=local_description,
                        server_description=server_description,
                        description_differs=description_differs,
                    )
                )

    # Find orphaned server variables (on server but not in local code)
    orphaned = [name for name in server_config.variables.keys() if name not in local_names]

    return VariableDiff(changes=changes, orphaned_server_variables=orphaned)


def _format_diff(diff: VariableDiff) -> str:
    """Format the diff for display to the user."""
    lines: list[str] = []

    creates = [c for c in diff.changes if c.change_type == 'create']
    updates = [c for c in diff.changes if c.change_type == 'update_schema']
    unchanged = [c for c in diff.changes if c.change_type == 'no_change']
    description_diffs = [c for c in diff.changes if c.description_differs]

    if creates:
        lines.append(f'\n{ANSI_GREEN}=== Variables to CREATE ==={ANSI_RESET}')
        for change in creates:
            lines.append(f'  {ANSI_GREEN}+ {change.name}{ANSI_RESET}')
            if change.local_description:
                lines.append(f'    Description: {change.local_description}')
            if change.initial_variant_value:
                lines.append(f'    Default variant: {change.initial_variant_value}')
            else:
                lines.append('    (No default variant - default is a function)')

    if updates:
        lines.append(f'\n{ANSI_YELLOW}=== Variables to UPDATE (schema changed) ==={ANSI_RESET}')
        for change in updates:
            lines.append(f'  {ANSI_YELLOW}~ {change.name}{ANSI_RESET}')
            if change.incompatible_variants:
                lines.append(f'    {ANSI_RED}Warning: Incompatible variants:{ANSI_RESET}')
                for compat in change.incompatible_variants:
                    lines.append(f'      - {compat.variant_key}: {compat.error}')

    if unchanged:
        lines.append(f'\n{ANSI_GRAY}=== No changes needed ({len(unchanged)} variables) ==={ANSI_RESET}')
        for change in unchanged:
            lines.append(f'  {ANSI_GRAY}  {change.name}{ANSI_RESET}')

    if diff.orphaned_server_variables:
        lines.append(f'\n{ANSI_GRAY}=== Server-only variables (not in local code) ==={ANSI_RESET}')
        for name in diff.orphaned_server_variables:
            lines.append(f'  {ANSI_GRAY}? {name}{ANSI_RESET}')

    # Show description differences as informational warnings
    if description_diffs:
        lines.append(f'\n{ANSI_CYAN}=== Description differences (informational) ==={ANSI_RESET}')
        lines.append(f'{ANSI_CYAN}Note: Different descriptions may be intentional for different codebases.{ANSI_RESET}')
        for change in description_diffs:
            lines.append(f'  {ANSI_CYAN}! {change.name}{ANSI_RESET}')
            local_desc = change.local_description or '(none)'
            server_desc = change.server_description or '(none)'
            lines.append(f'    Local:  {local_desc}')
            lines.append(f'    Server: {server_desc}')

    return '\n'.join(lines)


def _apply_changes(
    provider: VariableProvider,
    diff: VariableDiff,
    server_config: VariablesConfig,
) -> None:
    """Apply the changes using the provider."""
    for change in diff.changes:
        if change.change_type == 'create':
            _create_variable(provider, change)
        elif change.change_type == 'update_schema':  # pragma: no branch
            _update_variable_schema(provider, change, server_config)


def _create_variable(
    provider: VariableProvider,
    change: VariableChange,
) -> None:
    """Create a new variable via the provider."""
    from logfire.variables.config import Rollout, VariableConfig, Variant

    if change.initial_variant_value is not None:
        # Has a static default - create a 'default' variant with 100% rollout
        variants = {
            'default': Variant(
                key='default',
                serialized_value=change.initial_variant_value,
                description='Default value from code',
            )
        }
        rollout = Rollout(variants={'default': 1.0})
    else:
        # Default is a function - no server-side variant, empty rollout
        variants = {}
        rollout = Rollout(variants={})

    config = VariableConfig(
        name=change.name,
        description=change.local_description,
        variants=variants,
        rollout=rollout,
        overrides=[],
        json_schema=change.local_schema,
    )

    provider.create_variable(config)
    print(f'  {ANSI_GREEN}Created: {change.name}{ANSI_RESET}')


def _update_variable_schema(
    provider: VariableProvider,
    change: VariableChange,
    server_config: VariablesConfig,
) -> None:
    """Update an existing variable's schema via the provider."""
    from logfire.variables.config import VariableConfig

    # Get the existing config to preserve variants, rollout, overrides
    existing = server_config.variables.get(change.name)
    if existing is None:  # pragma: no cover
        # Should not happen, but handle gracefully
        print(f'  {ANSI_RED}Warning: Could not find existing config for {change.name}{ANSI_RESET}')
        return

    # Create updated config with new schema but preserve everything else
    config = VariableConfig(
        name=existing.name,
        description=existing.description,
        variants=existing.variants,
        rollout=existing.rollout,
        overrides=existing.overrides,
        json_schema=change.local_schema,
    )

    provider.update_variable(change.name, config)
    print(f'  {ANSI_YELLOW}Updated schema: {change.name}{ANSI_RESET}')


def _format_validation_report(report: ValidationReport) -> str:
    """Format a validation report for display to the user."""
    lines: list[str] = []

    if report.errors:
        lines.append(f'\n{ANSI_RED}=== Validation Errors ==={ANSI_RESET}')
        for error in report.errors:
            if error.variant_key is None:  # pragma: no cover
                lines.append(f'  {ANSI_RED}✗ {error.variable_name}: {error.error}{ANSI_RESET}')
            else:
                lines.append(f'  {ANSI_RED}✗ {error.variable_name} (variant: {error.variant_key}){ANSI_RESET}')
                # Format the error message, indenting each line
                error_lines = str(error.error).split('\n')
                for line in error_lines[:5]:  # Limit to first 5 lines
                    lines.append(f'      {line}')
                if len(error_lines) > 5:
                    lines.append(f'      ... ({len(error_lines) - 5} more lines)')

    if report.variables_not_on_server:
        lines.append(f'\n{ANSI_YELLOW}=== Variables Not Found on Server ==={ANSI_RESET}')
        for name in report.variables_not_on_server:
            lines.append(f'  {ANSI_YELLOW}? {name}{ANSI_RESET}')

    valid_count = report.variables_checked - len(report.errors) - len(report.variables_not_on_server)
    if valid_count > 0:
        lines.append(f'\n{ANSI_GREEN}=== Valid ({valid_count} variables) ==={ANSI_RESET}')

    # Show description differences as informational warnings
    if report.description_differences:
        lines.append(f'\n{ANSI_CYAN}=== Description differences (informational) ==={ANSI_RESET}')
        lines.append(f'{ANSI_CYAN}Note: Different descriptions may be intentional for different codebases.{ANSI_RESET}')
        for diff in report.description_differences:
            lines.append(f'  {ANSI_CYAN}! {diff.variable_name}{ANSI_RESET}')
            local_desc = diff.local_description or '(none)'
            server_desc = diff.server_description or '(none)'
            lines.append(f'    Local:  {local_desc}')
            lines.append(f'    Server: {server_desc}')

    return '\n'.join(lines)


class VariableProvider(ABC):
    """Abstract base class for variable value providers."""

    @abstractmethod
    def get_serialized_value(
        self,
        variable_name: str,
        targeting_key: str | None = None,
        attributes: Mapping[str, Any] | None = None,
    ) -> ResolvedVariable[str | None]:
        """Retrieve the serialized value for a variable.

        Args:
            variable_name: The name of the variable to resolve.
            targeting_key: Optional key for deterministic variant selection (e.g., user ID).
            attributes: Optional attributes for condition-based targeting rules.

        Returns:
            A ResolvedVariable containing the serialized value (or None if not found).
        """
        raise NotImplementedError

    def refresh(self, force: bool = False):
        """Refresh the value provider.

        Only relevant to remote providers where initial retrieval may be asynchronous.
        Calling this method is intended to block until an initial retrieval happens, but is not guaranteed
        to eagerly retrieve any updates if the provider implements some kind of caching; the `force` argument
        is provided as a way to ignore any caching.

        Args:
            force: Whether to force refresh. If using a provider with caching, setting this to `True` triggers a refresh
            ignoring the cache.
        """
        pass

    def shutdown(self):
        """Clean up any resources used by the provider."""
        pass

    def get_variable_config(self, name: str) -> VariableConfig | None:
        """Retrieve the full configuration for a variable.

        Args:
            name: The name of the variable.

        Returns:
            The VariableConfig if found, or None if the variable doesn't exist.

        Note:
            Subclasses should override this method to provide actual implementations.
            The default implementation returns None.
        """
        return None  # pragma: no cover

    def get_all_variables_config(self) -> VariablesConfig:
        """Retrieve all variable configurations.

        This is used by push_variables() to compute diffs.

        Returns:
            A VariablesConfig containing all variable configurations.
            Returns an empty VariablesConfig if no configs are available.
        """
        from logfire.variables.config import VariablesConfig

        return VariablesConfig(variables={})

    def create_variable(self, config: VariableConfig) -> VariableConfig:
        """Create a new variable configuration.

        Args:
            config: The configuration for the new variable.

        Returns:
            The created VariableConfig.

        Raises:
            VariableAlreadyExistsError: If a variable with this name already exists.

        Note:
            Subclasses should override this method to provide actual implementations.
            The default implementation emits a warning and returns the config unchanged.
        """
        warnings.warn(
            f'{type(self).__name__} does not persist variable writes',
            stacklevel=2,
        )
        return config

    def update_variable(self, name: str, config: VariableConfig) -> VariableConfig:
        """Update an existing variable configuration.

        Args:
            name: The name of the variable to update.
            config: The new configuration for the variable.

        Returns:
            The updated VariableConfig.

        Raises:
            VariableNotFoundError: If the variable does not exist.

        Note:
            Subclasses should override this method to provide actual implementations.
            The default implementation emits a warning and returns the config unchanged.
        """
        warnings.warn(
            f'{type(self).__name__} does not persist variable writes',
            stacklevel=2,
        )
        return config

    def delete_variable(self, name: str) -> None:
        """Delete a variable configuration.

        Args:
            name: The name of the variable to delete.

        Raises:
            VariableNotFoundError: If the variable does not exist.

        Note:
            Subclasses should override this method to provide actual implementations.
            The default implementation emits a warning.
        """
        warnings.warn(
            f'{type(self).__name__} does not persist variable writes',
            stacklevel=2,
        )

    def batch_update(self, updates: dict[str, VariableConfig | None]) -> None:
        """Update multiple variables atomically.

        This default implementation processes updates sequentially. Subclasses
        (especially remote providers) may override this to batch operations
        into a single API call for better performance.

        Args:
            updates: A mapping of variable names to their new configurations.
                Unrecognized names will be created.
                A None value means the variable should be deleted.
                All others will be updated.
        """
        for name, config in updates.items():
            if config is None:
                self.delete_variable(name)
            elif self.get_variable_config(name) is None:
                self.create_variable(config)
            else:
                self.update_variable(name, config)

    def push_variables(
        self,
        variables: list[Variable[Any]],
        *,
        dry_run: bool = False,
        yes: bool = False,
        strict: bool = False,
    ) -> bool:
        """Push variable definitions to this provider.

        This method syncs local variable definitions with the provider:
        - Creates new variables that don't exist in the provider
        - Updates JSON schemas for existing variables if they've changed
        - Warns about existing variants that are incompatible with new schemas

        Args:
            variables: Variable instances to push.
            dry_run: If True, only show what would change without applying.
            yes: If True, skip confirmation prompt.
            strict: If True, fail if any existing variants are incompatible with new schemas.

        Returns:
            True if changes were applied (or would be applied in dry_run mode), False otherwise.
        """
        if not variables:
            print('No variables to push. Create variables using logfire.var() first.')
            return False

        print(f'Using provider: {type(self).__name__}')

        # Refresh the provider to ensure we have the latest config
        try:
            self.refresh(force=True)
        except Exception as e:
            print(f'{ANSI_YELLOW}Warning: Could not refresh provider: {e}{ANSI_RESET}', file=sys.stderr)

        # Get current variable configs from provider
        try:
            server_config = self.get_all_variables_config()
        except Exception as e:
            print(f'{ANSI_RED}Error fetching current config: {e}{ANSI_RESET}', file=sys.stderr)
            return False

        # Compute diff
        diff = _compute_diff(variables, server_config)

        # Show diff
        print(_format_diff(diff))

        if not diff.has_changes:
            print(f'\n{ANSI_GREEN}No changes needed. Provider is up to date.{ANSI_RESET}')
            return False

        # Check for incompatible variants
        incompatible_changes = [c for c in diff.changes if c.change_type == 'update_schema' and c.incompatible_variants]
        if incompatible_changes:
            message = f'Some changes will result in variants incompatible with the new schema.\n{incompatible_changes}'
            if strict:
                print(
                    f'\n{ANSI_RED}Error: {message}\nRemove --strict flag to proceed anyway.{ANSI_RESET}',
                    file=sys.stderr,
                )
                return False
            else:
                print(
                    f'\n{ANSI_YELLOW}Warning: {message}\n',
                    file=sys.stderr,
                )

        if dry_run:
            print(f'\n{ANSI_YELLOW}Dry run mode - no changes applied.{ANSI_RESET}')
            return True

        # Confirm with user
        if not yes:  # pragma: no cover
            print()
            try:
                response_input = input('Apply these changes? [y/N] ')
            except (EOFError, KeyboardInterrupt):
                print('\nAborted.')
                return False

            if response_input.lower() not in ('y', 'yes'):
                print('Aborted.')
                return False

        # Apply changes
        print('\nApplying changes...')
        try:
            _apply_changes(self, diff, server_config)
        except Exception as e:
            print(f'{ANSI_RED}Error applying changes: {e}{ANSI_RESET}', file=sys.stderr)
            return False

        print(f'\n{ANSI_GREEN}Done! Variables synced successfully.{ANSI_RESET}')
        return True

    def validate_variables(
        self,
        variables: list[Variable[Any]],
    ) -> bool:
        """Validate that provider-side variable variants match local type definitions.

        This method fetches the current variable configuration from the provider and
        validates that all variant values can be deserialized to the expected types
        defined in the local Variable instances.

        Args:
            variables: Variable instances to validate.

        Returns:
            True if all variables validated successfully, False if there were errors.
        """
        if not variables:
            print('No variables to validate. Create variables using logfire.var() first.')
            return True  # No variables to validate is not an error

        print(f'Using provider: {type(self).__name__}')

        # Refresh the provider to ensure we have the latest config
        try:
            self.refresh(force=True)
        except Exception as e:
            print(f'{ANSI_YELLOW}Warning: Could not refresh provider: {e}{ANSI_RESET}', file=sys.stderr)

        # Get current variable configs from provider
        try:
            server_config = self.get_all_variables_config()
        except Exception as e:
            print(f'{ANSI_RED}Error fetching current config: {e}{ANSI_RESET}', file=sys.stderr)
            return False

        # Find variables not on server
        variables_not_on_server = [v.name for v in variables if v.name not in server_config.variables]

        # Filter to variables that are on the server
        variables_on_server = [v for v in variables if v.name in server_config.variables]

        # Get validation errors
        error_dict = server_config.get_validation_errors(variables_on_server)

        # Build report
        errors: list[VariantValidationError] = []
        for var_name, variant_errors in error_dict.items():
            for variant_key, error in variant_errors.items():
                errors.append(
                    VariantValidationError(
                        variable_name=var_name,
                        variant_key=variant_key,
                        error=error,
                    )
                )

        # Check for description differences
        description_differences: list[DescriptionDifference] = []
        for variable in variables_on_server:
            server_var = server_config.variables.get(variable.name)
            if server_var is not None:  # pragma: no branch
                # Normalize: treat None and empty string as equivalent
                local_desc = variable.description or None
                server_desc = server_var.description or None
                if local_desc != server_desc:
                    description_differences.append(
                        DescriptionDifference(
                            variable_name=variable.name,
                            local_description=variable.description,
                            server_description=server_var.description,
                        )
                    )

        # TODO: Return the ValidationReport rather than just a boolean; maybe make it a kwarg to do something with printing?
        report = ValidationReport(
            errors=errors,
            variables_checked=len(variables),
            variables_not_on_server=variables_not_on_server,
            description_differences=description_differences,
        )

        # Print report
        print(_format_validation_report(report))

        if report.has_errors:
            error_count = len(report.errors) + len(report.variables_not_on_server)
            print(f'\n{ANSI_RED}Validation failed: {error_count} error(s) found.{ANSI_RESET}')
            return False
        else:
            print(f'\n{ANSI_GREEN}Validation passed: All {report.variables_checked} variable(s) are valid.{ANSI_RESET}')
            return True


@dataclass
class NoOpVariableProvider(VariableProvider):
    """A variable provider that always returns None, used when no provider is configured."""

    def get_serialized_value(
        self,
        variable_name: str,
        targeting_key: str | None = None,
        attributes: Mapping[str, Any] | None = None,
    ) -> ResolvedVariable[str | None]:
        """Return None for all variable lookups.

        Args:
            variable_name: The name of the variable to resolve (ignored).
            targeting_key: Optional key for deterministic variant selection (ignored).
            attributes: Optional attributes for condition-based targeting rules (ignored).

        Returns:
            A ResolvedVariable with value=None.
        """
        return ResolvedVariable(name=variable_name, value=None, _reason='no_provider')

    def get_variable_config(self, name: str) -> VariableConfig | None:
        """Return None for all variable lookups.

        Args:
            name: The name of the variable (ignored).

        Returns:
            Always None since no provider is configured.
        """
        return None

    def push_variables(
        self,
        variables: list[Variable[Any]],
        *,
        dry_run: bool = False,
        yes: bool = False,
        strict: bool = False,
    ) -> bool:
        """No-op implementation that prints a message about missing provider configuration.

        Returns:
            Always False since no provider is configured.
        """
        print('No variable provider configured. Configure a provider using logfire.configure(variables=...).')
        return False

    def validate_variables(
        self,
        variables: list[Variable[Any]],
    ) -> bool:
        """No-op implementation that prints a message about missing provider configuration.

        Returns:
            Always True since there's nothing to validate without a provider.
        """
        print('No variable provider configured. Configure a provider using logfire.configure(variables=...).')
        return True
