"""Variable push functionality for syncing local variables to Logfire server."""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from pydantic import ValidationError

from logfire.variables.variable import Variable, is_resolve_function

if TYPE_CHECKING:
    from logfire.api_client import LogfireAPIClient

__all__ = ('push_variables', 'validate_variables', 'VariableDiff', 'VariableChange', 'DescriptionDifference')


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


def _get_json_schema(variable: Variable[Any]) -> dict[str, Any]:
    """Get the JSON schema for a variable's type."""
    return variable.type_adapter.json_schema()


def _get_default_serialized(variable: Variable[Any]) -> str | None:
    """Get the serialized default value for a variable.

    Returns None if the default is a ResolveFunction (can't serialize a function).
    """
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
    server_config: dict[str, Any],
) -> VariableDiff:
    """Compute the diff between local variables and server config."""
    changes: list[VariableChange] = []
    local_names = {v.name for v in variables}
    server_variables = server_config.get('variables', {})

    for variable in variables:
        local_schema = _get_json_schema(variable)
        local_description = variable.description
        server_var = server_variables.get(variable.name)

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
            server_schema = server_var.get('json_schema')
            server_description = server_var.get('description')

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
                for variant_key, variant_data in server_var.get('variants', {}).items():
                    compat = _check_variant_compatibility(
                        variable,
                        variant_key,
                        variant_data.get('serialized_value', ''),
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
                        server_id=server_var.get('id'),
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
    orphaned = [name for name in server_variables.keys() if name not in local_names]

    return VariableDiff(changes=changes, orphaned_server_variables=orphaned)


def _format_diff(diff: VariableDiff) -> str:
    """Format the diff for display to the user."""
    lines: list[str] = []

    creates = [c for c in diff.changes if c.change_type == 'create']
    updates = [c for c in diff.changes if c.change_type == 'update_schema']
    unchanged = [c for c in diff.changes if c.change_type == 'no_change']
    description_diffs = [c for c in diff.changes if c.description_differs]

    if creates:
        lines.append('\n\033[32m=== Variables to CREATE ===\033[0m')
        for change in creates:
            lines.append(f'  \033[32m+ {change.name}\033[0m')
            if change.local_description:
                lines.append(f'    Description: {change.local_description}')
            if change.initial_variant_value:
                lines.append(f'    Default variant: {change.initial_variant_value}')
            else:
                lines.append('    (No default variant - default is a function)')

    if updates:
        lines.append('\n\033[33m=== Variables to UPDATE (schema changed) ===\033[0m')
        for change in updates:
            lines.append(f'  \033[33m~ {change.name}\033[0m')
            if change.incompatible_variants:
                lines.append('    \033[31mWarning: Incompatible variants:\033[0m')
                for compat in change.incompatible_variants:
                    lines.append(f'      - {compat.variant_key}: {compat.error}')

    if unchanged:
        lines.append(f'\n\033[90m=== No changes needed ({len(unchanged)} variables) ===\033[0m')
        for change in unchanged:
            lines.append(f'  \033[90m  {change.name}\033[0m')

    if diff.orphaned_server_variables:
        lines.append('\n\033[90m=== Server-only variables (not in local code) ===\033[0m')
        for name in diff.orphaned_server_variables:
            lines.append(f'  \033[90m? {name}\033[0m')

    # Show description differences as informational warnings
    if description_diffs:
        lines.append('\n\033[36m=== Description differences (informational) ===\033[0m')
        lines.append('\033[36mNote: Different descriptions may be intentional for different codebases.\033[0m')
        for change in description_diffs:
            lines.append(f'  \033[36m! {change.name}\033[0m')
            local_desc = change.local_description or '(none)'
            server_desc = change.server_description or '(none)'
            lines.append(f'    Local:  {local_desc}')
            lines.append(f'    Server: {server_desc}')

    return '\n'.join(lines)


class _VariablesClient:
    """Wrapper for variables API operations using LogfireAPIClient.

    The underlying client methods use token-scoped endpoints that derive
    the project from the API token itself.
    """

    def __init__(self, client: LogfireAPIClient):
        self._client = client

    def get_variables_config(self) -> dict[str, Any]:
        return self._client.get_variables_config()

    def create_variable(self, body: dict[str, Any]) -> dict[str, Any]:
        return self._client.create_variable(body)

    def update_variable(self, variable_name: str, body: dict[str, Any]) -> dict[str, Any]:
        return self._client.update_variable(variable_name, body)


def _apply_changes(
    client: _VariablesClient,
    diff: VariableDiff,
) -> None:
    """Apply the changes to the server."""
    for change in diff.changes:
        if change.change_type == 'create':
            _create_variable(client, change)
        elif change.change_type == 'update_schema':
            _update_variable_schema(client, change)


def _create_variable(
    client: _VariablesClient,
    change: VariableChange,
) -> None:
    """Create a new variable on the server."""
    body: dict[str, Any] = {
        'name': change.name,
        'json_schema': change.local_schema,
        'description': change.local_description,
    }

    if change.initial_variant_value is not None:
        # Has a static default - create a 'default' variant with 100% rollout
        body['variants'] = {
            'default': {
                'serialized_value': change.initial_variant_value,
                'description': 'Default value from code',
            }
        }
        body['rollout'] = {'variants': {'default': 1.0}}
    else:
        # Default is a function - no server-side variant, empty rollout
        body['variants'] = {}
        body['rollout'] = {'variants': {}}

    body['overrides'] = []

    client.create_variable(body)
    print(f'  \033[32mCreated: {change.name}\033[0m')


def _update_variable_schema(
    client: _VariablesClient,
    change: VariableChange,
) -> None:
    """Update an existing variable's schema on the server."""
    body = {
        'json_schema': change.local_schema,
    }

    client.update_variable(change.name, body)
    print(f'  \033[33mUpdated schema: {change.name}\033[0m')


def _get_variables_client() -> tuple[_VariablesClient, str] | None:
    """Create a variables client from LOGFIRE_API_TOKEN environment variable.

    The API token must be scoped to a specific project. The project is derived
    from the token itself.

    Returns:
        Tuple of (client, base_url) if successful, None otherwise.
    """
    import os

    from logfire.api_client import LOGFIRE_API_TOKEN_ENV, LogfireAPIClient

    api_token = os.environ.get(LOGFIRE_API_TOKEN_ENV)
    if not api_token:
        print(
            f'\033[31mError: {LOGFIRE_API_TOKEN_ENV} environment variable is not set.\n'
            'The variables API requires a project-scoped API token.\033[0m',
            file=sys.stderr,
        )
        return None

    try:
        client = LogfireAPIClient(api_token=api_token)
    except Exception as e:
        print(f'\033[31mError: Invalid API token: {e}\033[0m', file=sys.stderr)
        return None

    return _VariablesClient(client), client.base_url


# TODO: Make it possible to manually provide the API token in this call
def push_variables(
    variables: list[Variable[Any]] | None = None,
    *,
    dry_run: bool = False,
    yes: bool = False,
    strict: bool = False,
) -> bool:
    """Push variable definitions to the Logfire server.

    This function syncs local variable definitions with the server:
    - Creates new variables that don't exist on the server
    - Updates JSON schemas for existing variables if they've changed
    - Warns about existing variants that are incompatible with new schemas

    Authentication: Requires the LOGFIRE_API_TOKEN environment variable to be set
    with a project-scoped API token. The project is derived from the token itself.

    Args:
        variables: Variable instances to push to the server. If None, all variables
            registered with the default Logfire instance will be pushed.
        dry_run: If True, only show what would change without applying.
        yes: If True, skip confirmation prompt.
        strict: If True, fail if any existing variants are incompatible with new schemas.

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
    import logfire as logfire_module

    if variables is None:
        variables = logfire_module.DEFAULT_LOGFIRE_INSTANCE.get_variables()

    if not variables:
        print('No variables to push. Create variables using logfire.var() first.')
        return False

    # Get variables client from API token
    result = _get_variables_client()
    if result is None:
        return False
    client, base_url = result
    print(f'Using API token (base URL: {base_url})')

    # Fetch current server config
    try:
        server_config = client.get_variables_config()
    except Exception as e:
        print(f'\033[31mError fetching server config: {e}\033[0m', file=sys.stderr)
        return False

    # Compute diff
    diff = _compute_diff(variables, server_config)

    # Show diff
    print(_format_diff(diff))

    if not diff.has_changes:
        print('\n\033[32mNo changes needed. Server is up to date.\033[0m')
        return False

    # Check for incompatible variants in strict mode
    if strict:
        has_incompatible = any(c.incompatible_variants for c in diff.changes if c.change_type == 'update_schema')
        if has_incompatible:
            print(
                '\n\033[31mError: Some existing variants are incompatible with the new schema. '
                'Remove --strict flag to proceed anyway.\033[0m',
                file=sys.stderr,
            )
            return False

    if dry_run:
        print('\n\033[33mDry run mode - no changes applied.\033[0m')
        return True

    # Confirm with user
    if not yes:
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
        _apply_changes(client, diff)
    except Exception as e:
        print(f'\033[31mError applying changes: {e}\033[0m', file=sys.stderr)
        return False

    print('\n\033[32mDone! Variables synced successfully.\033[0m')
    return True


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


def _format_validation_report(report: ValidationReport) -> str:
    """Format a validation report for display to the user."""
    lines: list[str] = []

    if report.errors:
        lines.append('\n\033[31m=== Validation Errors ===\033[0m')
        for error in report.errors:
            if error.variant_key is None:
                lines.append(f'  \033[31m✗ {error.variable_name}: {error.error}\033[0m')
            else:
                lines.append(f'  \033[31m✗ {error.variable_name} (variant: {error.variant_key})\033[0m')
                # Format the error message, indenting each line
                error_lines = str(error.error).split('\n')
                for line in error_lines[:5]:  # Limit to first 5 lines
                    lines.append(f'      {line}')
                if len(error_lines) > 5:
                    lines.append(f'      ... ({len(error_lines) - 5} more lines)')

    if report.variables_not_on_server:
        lines.append('\n\033[33m=== Variables Not Found on Server ===\033[0m')
        for name in report.variables_not_on_server:
            lines.append(f'  \033[33m? {name}\033[0m')

    valid_count = report.variables_checked - len(report.errors) - len(report.variables_not_on_server)
    if valid_count > 0:
        lines.append(f'\n\033[32m=== Valid ({valid_count} variables) ===\033[0m')

    # Show description differences as informational warnings
    if report.description_differences:
        lines.append('\n\033[36m=== Description differences (informational) ===\033[0m')
        lines.append('\033[36mNote: Different descriptions may be intentional for different codebases.\033[0m')
        for diff in report.description_differences:
            lines.append(f'  \033[36m! {diff.variable_name}\033[0m')
            local_desc = diff.local_description or '(none)'
            server_desc = diff.server_description or '(none)'
            lines.append(f'    Local:  {local_desc}')
            lines.append(f'    Server: {server_desc}')

    return '\n'.join(lines)


def validate_variables(
    variables: list[Variable[Any]] | None = None,
) -> bool:
    """Validate that server-side variable variants match local type definitions.

    This function fetches the current variable configuration from the server and
    validates that all variant values can be deserialized to the expected types
    defined in the local Variable instances.

    Authentication: Requires the LOGFIRE_API_TOKEN environment variable to be set
    with a project-scoped API token. The project is derived from the token itself.

    Args:
        variables: Variable instances to validate. If None, all variables
            registered with the default Logfire instance will be validated.

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
    import logfire as logfire_module
    from logfire.variables.config import VariablesConfig

    if variables is None:
        variables = logfire_module.DEFAULT_LOGFIRE_INSTANCE.get_variables()

    if not variables:
        print('No variables to validate. Create variables using logfire.var() first.')
        return True  # No variables to validate is not an error

    # Get variables client from API token
    result = _get_variables_client()
    if result is None:
        return False
    client, base_url = result
    print(f'Using API token (base URL: {base_url})')

    # Fetch current server config
    try:
        server_config_raw = client.get_variables_config()
    except Exception as e:
        print(f'\033[31mError fetching server config: {e}\033[0m', file=sys.stderr)
        return False

    # Parse into VariablesConfig
    try:
        config = VariablesConfig.validate_python(server_config_raw)
    except Exception as e:
        print(f'\033[31mError parsing server config: {e}\033[0m', file=sys.stderr)
        return False

    # Find variables not on server
    variables_not_on_server = [v.name for v in variables if v.name not in config.variables]

    # Filter to variables that are on the server
    variables_on_server = [v for v in variables if v.name in config.variables]

    # Get validation errors
    error_dict = config.get_validation_errors(variables_on_server)

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
        server_var = config.variables.get(variable.name)
        if server_var is not None:
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
        print(f'\n\033[31mValidation failed: {error_count} error(s) found.\033[0m')
        return False
    else:
        print(f'\n\033[32mValidation passed: All {report.variables_checked} variable(s) are valid.\033[0m')
        return True
