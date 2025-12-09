from dataclasses import dataclass
from logfire.variables.variable import Variable
from typing import Any

__all__ = ['push_variables', 'validate_variables', 'VariableDiff', 'VariableChange']

@dataclass
class VariantCompatibility:
    """Result of checking a variant's compatibility with a schema."""
    variant_key: str
    serialized_value: str
    is_compatible: bool
    error: str | None = ...

@dataclass
class VariableChange:
    """Represents a change to be made to a variable."""
    name: str
    change_type: str
    local_schema: dict[str, Any] | None = ...
    server_schema: dict[str, Any] | None = ...
    initial_variant_value: str | None = ...
    incompatible_variants: list[VariantCompatibility] | None = ...
    server_id: str | None = ...

@dataclass
class VariableDiff:
    """Represents the diff between local and server variables."""
    changes: list[VariableChange]
    orphaned_server_variables: list[str]
    @property
    def has_changes(self) -> bool:
        """Return True if there are any changes to apply."""

def push_variables(variables: list[Variable[Any]] | None = None, *, dry_run: bool = False, yes: bool = False, strict: bool = False, data_dir: str | None = None) -> bool:
    """Push variable definitions to the Logfire server.

    This function syncs local variable definitions with the server:
    - Creates new variables that don't exist on the server
    - Updates JSON schemas for existing variables if they've changed
    - Warns about existing variants that are incompatible with new schemas

    Args:
        variables: Variable instances to push to the server. If None, all variables
            registered with the default Logfire instance will be pushed.
        dry_run: If True, only show what would change without applying.
        yes: If True, skip confirmation prompt.
        strict: If True, fail if any existing variants are incompatible with new schemas.
        data_dir: Directory containing Logfire credentials. Defaults to '.logfire'.

    Returns:
        True if changes were applied (or would be applied in dry_run mode), False otherwise.

    Example:
        ```python
        import logfire

        feature_enabled = logfire.var(name='feature-enabled', default=False, type=bool)
        max_retries = logfire.var(name='max-retries', default=3, type=int)

        if __name__ == '__main__':
            # Push all registered variables
            logfire.push_variables()

            # Or push specific variables only
            logfire.push_variables([feature_enabled])
        ```
    """

@dataclass
class VariantValidationError:
    """Represents a validation error for a specific variant."""
    variable_name: str
    variant_key: str | None
    error: Exception

@dataclass
class ValidationReport:
    """Report of variable validation results."""
    errors: list[VariantValidationError]
    variables_checked: int
    variables_not_on_server: list[str]
    @property
    def has_errors(self) -> bool:
        """Return True if there are any validation errors."""

def validate_variables(variables: list[Variable[Any]] | None = None, *, data_dir: str | None = None) -> bool:
    """Validate that server-side variable variants match local type definitions.

    This function fetches the current variable configuration from the server and
    validates that all variant values can be deserialized to the expected types
    defined in the local Variable instances.

    Args:
        variables: Variable instances to validate. If None, all variables
            registered with the default Logfire instance will be validated.
        data_dir: Directory containing Logfire credentials. Defaults to '.logfire'.

    Returns:
        True if all variables validated successfully, False if there were errors.

    Example:
        ```python
        import logfire

        feature_enabled = logfire.var(name='feature-enabled', default=False, type=bool)
        max_retries = logfire.var(name='max-retries', default=3, type=int)

        if __name__ == '__main__':
            # Validate all registered variables
            logfire.validate_variables()

            # Or validate specific variables only
            logfire.validate_variables([feature_enabled])
        ```
    """
