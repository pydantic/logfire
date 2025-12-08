"""Variable push functionality for syncing local variables to Logfire server."""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from pydantic import ValidationError

from logfire.variables.variable import Variable, is_resolve_function

if TYPE_CHECKING:
    from logfire._internal.client import LogfireClient

__all__ = ('push_variables', 'VariableDiff', 'VariableChange')


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
    change_type: str  # 'create', 'update_schema', 'no_change'
    local_schema: dict[str, Any] | None = None
    server_schema: dict[str, Any] | None = None
    initial_variant_value: str | None = None  # JSON serialized
    incompatible_variants: list[VariantCompatibility] | None = None
    server_id: str | None = None  # For updates


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
                )
            )
        else:
            # Variable exists - check if schema changed
            server_schema = server_var.get('json_schema')

            # Normalize schemas for comparison (remove $defs if empty, etc.)
            local_normalized = json.dumps(local_schema, sort_keys=True)
            server_normalized = json.dumps(server_schema, sort_keys=True) if server_schema else '{}'

            if local_normalized != server_normalized:
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
                    )
                )
            else:
                # No change needed
                changes.append(
                    VariableChange(
                        name=variable.name,
                        change_type='no_change',
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

    if creates:
        lines.append('\n\033[32m=== Variables to CREATE ===\033[0m')
        for change in creates:
            lines.append(f'  \033[32m+ {change.name}\033[0m')
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

    return '\n'.join(lines)


def _apply_changes(
    client: LogfireClient,
    organization: str,
    project: str,
    diff: VariableDiff,
) -> None:
    """Apply the changes to the server."""
    for change in diff.changes:
        if change.change_type == 'create':
            _create_variable(client, organization, project, change)
        elif change.change_type == 'update_schema':
            _update_variable_schema(client, organization, project, change)


def _create_variable(
    client: LogfireClient,
    organization: str,
    project: str,
    change: VariableChange,
) -> None:
    """Create a new variable on the server."""
    body: dict[str, Any] = {
        'name': change.name,
        'json_schema': change.local_schema,
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

    client.create_variable(organization, project, body)
    print(f'  \033[32mCreated: {change.name}\033[0m')


def _update_variable_schema(
    client: LogfireClient,
    organization: str,
    project: str,
    change: VariableChange,
) -> None:
    """Update an existing variable's schema on the server."""
    server_id = change.server_id
    if not server_id:
        # Need to look up the variable by name to get its ID
        var_data = client.get_variable_by_name(organization, project, change.name)
        server_id = var_data['id']

    body = {
        'json_schema': change.local_schema,
    }

    client.update_variable(organization, project, server_id, body)
    print(f'  \033[33mUpdated schema: {change.name}\033[0m')


def _get_project_credentials(data_dir: str | None = None) -> tuple[str, str]:
    """Get the organization and project from local credentials.

    Args:
        data_dir: Optional path to the data directory. Defaults to '.logfire'.

    Returns:
        Tuple of (organization, project_name)

    Raises:
        RuntimeError: If credentials are not found or cannot determine organization.
    """
    from pathlib import Path
    from urllib.parse import urlparse

    from logfire._internal.config import LogfireCredentials

    creds_dir = Path(data_dir) if data_dir else Path('.logfire')
    creds = LogfireCredentials.load_creds_file(creds_dir)

    if creds is None:
        raise RuntimeError(
            f'No Logfire credentials found in {creds_dir.resolve()}. '
            'Run your application with LOGFIRE_TOKEN set, '
            'or use `logfire projects use` to select a project.'
        )

    # Parse org and project from project_url
    # project_url is like: https://logfire.pydantic.dev/org-name/project-name
    parsed = urlparse(creds.project_url)
    path_parts = [p for p in parsed.path.split('/') if p]

    if len(path_parts) >= 2:
        return path_parts[0], path_parts[1]

    # Fallback: try to get from the project list using the project_name
    raise RuntimeError(
        f'Could not determine organization from project URL: {creds.project_url}. '
        'Expected format: https://logfire.pydantic.dev/org/project'
    )


def push_variables(
    variables: list[Variable[Any]] | None = None,
    *,
    dry_run: bool = False,
    yes: bool = False,
    strict: bool = False,
    data_dir: str | None = None,
) -> bool:
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
    import logfire as logfire_module
    from logfire._internal.client import LogfireClient

    if variables is None:
        variables = logfire_module.DEFAULT_LOGFIRE_INSTANCE.get_variables()

    if not variables:
        print('No variables to push. Create variables using logfire.var() first.')
        return False

    # Get credentials
    try:
        organization, project = _get_project_credentials(data_dir)
    except RuntimeError as e:
        print(f'\033[31mError: {e}\033[0m', file=sys.stderr)
        return False

    print(f'Syncing variables for project: {organization}/{project}')

    # Create client with user auth
    try:
        client = LogfireClient.from_url(None)
    except Exception as e:
        print('\033[31mError: Failed to authenticate. Run `logfire auth` first.\033[0m', file=sys.stderr)
        print(f'\033[31m{e}\033[0m', file=sys.stderr)
        return False

    # Fetch current server config
    try:
        server_config = client.get_variables_config(organization, project)
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
        has_incompatible = any(
            c.incompatible_variants for c in diff.changes if c.change_type == 'update_schema'
        )
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
        _apply_changes(client, organization, project, diff)
    except Exception as e:
        print(f'\033[31mError applying changes: {e}\033[0m', file=sys.stderr)
        return False

    print('\n\033[32mDone! Variables synced successfully.\033[0m')
    return True
