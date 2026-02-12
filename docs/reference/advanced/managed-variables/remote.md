# Remote Variables

When connected to Logfire, variables are managed through the Logfire UI. This is the recommended setup for production.

To enable remote variables, you can explicitly opt in using `VariablesOptions`:

```python skip="true"
import logfire
# Enable remote variables
logfire.configure(
    variables=logfire.VariablesOptions(),
)

# Define your variables
agent_config = logfire.var(
    name='support_agent_config',
    type=AgentConfig,
    default=AgentConfig(...),
)
```

!!! tip "Automatic Remote Variables"
    If `LOGFIRE_API_KEY` is set in your environment, variable APIs will **automatically** use the remote provider without needing `variables=VariablesOptions()` in `configure()`. The first time a variable is resolved, the SDK detects the API key and lazily initializes the remote provider with default options. You only need to pass `variables=VariablesOptions(...)` explicitly if you want to customize options like `polling_interval` or `block_before_first_resolve`.

!!! note "API Key Required"
    Remote variables require an API key with the `project:read_variables` scope (or `project:read_external_variables` for access to external variables only). This is different from the write token (`LOGFIRE_TOKEN`) used to send traces and logs. Set the API key via the `LOGFIRE_API_KEY` environment variable or pass it directly to `VariablesOptions(api_key=...)`. See [External and Internal Variables](#external-and-internal-variables) for details on the different scopes.

**How remote variables work:**

1. Your application connects to Logfire using your API key
2. Variable configurations (including all versions and labels) are fetched from the Logfire API
3. A background thread polls for updates (default: every 60 seconds)
4. If available, the SDK listens for Server-Sent Events (SSE) on `GET /v1/variable-updates/` and triggers an immediate refresh
5. When you create a new version, move a label, or change a rollout in the UI, running applications pick up the change automatically via SSE or the next poll

**Configuration options:**

```python skip="true"
from datetime import timedelta

logfire.configure(
    variables=logfire.VariablesOptions(
        # Block until first fetch completes (default: True)
        # Set to False if you want the app to start immediately using defaults
        block_before_first_resolve=True,
        # How often to poll for updates (default: 60 seconds)
        polling_interval=timedelta(seconds=60),
    ),
)
```

## OpenFeature (OFREP) Endpoints

Logfire exposes managed variables via the OpenFeature Remote Evaluation Protocol (OFREP). These endpoints evaluate variables as feature flags using a targeting context.

**Endpoints (API base URL + paths):**

```text
POST /v1/ofrep/v1/evaluate/flags/{key}
POST /v1/ofrep/v1/evaluate/flags
```

**Request body (single or bulk):**

```json
{
  "context": {
    "targetingKey": "user-123",
    "plan": "enterprise",
    "region": "us-east"
  }
}
```

- `targetingKey` is required and is used for deterministic rollout selection.
- Any additional fields in `context` become attributes for override rules.
- The OFREP response maps labels to the `variant` field for compatibility with OpenFeature clients.

**Caching (bulk endpoint):**

- The bulk endpoint returns an `ETag` header.
- If the client sends `If-None-Match` with the same value, the server returns `304 Not Modified`.

These endpoints require an API key with the `project:read_variables` or `project:read_external_variables` scope (see below).

For a step-by-step guide on using OFREP to evaluate feature flags in a web frontend or other client application, see [Client-Side Feature Flags with OFREP](../../../how-to-guides/client-side-feature-flags.md).

## External and Internal Variables

By default, variables are **internal** — they are only accessible with an API key that has the full `project:read_variables` scope. You can mark a variable as **external** to make it accessible with the more restricted `project:read_external_variables` scope.

This distinction is useful when you need to read variable values from less trusted environments (e.g., client-side applications, third-party integrations, or edge services) without exposing your entire variable configuration:

- **Internal variables** (default): Only accessible with `project:read_variables`. Use this for sensitive configuration like internal prompts, pricing parameters, or anything you don't want exposed to client-side code.
- **External variables**: Accessible with either `project:read_variables` or `project:read_external_variables`. Use this for configuration that is safe to expose, like feature flags, UI theme settings, or public-facing behavior toggles.

**API key scopes for variables:**

| Scope | Description |
|-------|-------------|
| `project:read_variables` | Read all variables (both external and internal) |
| `project:read_external_variables` | Read only variables marked as external |
| `project:write_variables` | Create, update, and delete variables and variable types |

**Setting a variable as external:**

You can set a variable as external in the Logfire UI when creating a variable (via the "External" toggle on the create form) or on the variable's **Settings** tab. You can also set the `external` field when creating or updating a variable via the API. Variables default to internal (`external: false`) when created.

```python skip="true"
# When pushing variables, the 'external' field can be set in the variable definition
# via the API. For example, using the bulk upsert endpoint:
import httpx

httpx.post(
    'https://logfire-api.pydantic.dev/v1/variables/bulk/',
    headers={'Authorization': 'Bearer YOUR_API_KEY'},
    json=[
        {
            'name': 'feature_flag',
            'json_schema': {'type': 'boolean'},
            'rollout': {'labels': {}},
            'overrides': [],
            'external': True,  # Makes this variable accessible with read_external_variables scope
        },
    ],
)
```

**Typical setup:**

1. Create an API key with `project:read_variables` for your backend services (full access to all variables)
2. Create a separate API key with only `project:read_external_variables` for client-side or less trusted environments
3. Mark variables as external that are safe to expose to those environments

!!! note "OFREP and external variables"
    The OFREP endpoints (`/v1/ofrep/v1/evaluate/flags/...`) accept both `project:read_variables` and `project:read_external_variables` scopes. When using `project:read_external_variables`, only variables marked as external are returned in evaluations. This makes OFREP suitable for client-side feature flag evaluation with restricted API keys.

## Pushing Variables from Code

Instead of manually creating variables in the Logfire UI, you can push your variable definitions directly from your code using `logfire.variables_push()`.

The primary benefit of pushing from code is **automatic JSON schema generation**. When you use a Pydantic model as your variable type, `logfire.variables_push()` automatically generates the JSON schema from your model definition. This means the Logfire UI will validate version values against your schema, catching type errors before they reach production. Creating these schemas manually in the UI would be tedious and error-prone, especially for complex nested models.

```python skip="true"
from pydantic import BaseModel

import logfire
logfire.configure(
    variables=logfire.VariablesOptions(),
)


class AgentConfig(BaseModel):
    """Configuration for an AI agent."""

    instructions: str
    model: str
    temperature: float
    max_tokens: int


# Define your variables
agent_config = logfire.var(
    name='agent_config',
    type=AgentConfig,
    default=AgentConfig(
        instructions='You are a helpful assistant.',
        model='openai:gpt-4o-mini',
        temperature=0.7,
        max_tokens=500,
    ),
)

# Push all registered variables to the remote provider
if __name__ == '__main__':
    logfire.variables_push()
```

When you run this script, it will:

1. Compare your local variable definitions with what exists in Logfire
2. Show you a diff of what will be created or updated
3. Prompt for confirmation before applying changes

!!! note "Metadata only"
    `logfire.variables_push()` syncs **metadata only** — the variable name, description, JSON schema, rollout configuration, and overrides. It does **not** create versions or labels. Instead, it stores your code's default value as an "example" that can be used as a template when creating versions in the Logfire UI. You create versions and assign labels through the UI.

**Example output:**

```
=== Variables to CREATE ===
  + agent_config
    Example value: {"instructions":"You are a helpful assistant.","model":"openai:gpt-4o-mini","temperature":0.7,"max_tokens":500}

Apply these changes? [y/N] y

Applying changes...
Successfully applied changes.
```

**Options:**

| Parameter | Description |
|-----------|-------------|
| `variables` | List of specific variables to push. If not provided, all registered variables are pushed. |
| `dry_run` | If `True`, shows what would change without actually applying changes. |
| `yes` | If `True`, skips the confirmation prompt. |
| `strict` | If `True`, fails if any existing label values in Logfire are incompatible with your new schema. |

**Pushing specific variables:**

```python skip="true"
feature_flag = logfire.var(name='feature_enabled', type=bool, default=False)
max_retries = logfire.var(name='max_retries', type=int, default=3)

# Push only the feature flag
logfire.variables_push([feature_flag])

# Dry run to see what would change
logfire.variables_push(dry_run=True)

# Skip confirmation prompt (useful in CI/CD)
logfire.variables_push(yes=True)
```

!!! note "Schema Updates"
    When you push a variable that already exists in Logfire, `logfire.variables_push()` will update the JSON schema if it has changed but will preserve existing versions, labels, and rollout configurations. If existing label values are incompatible with the new schema, you'll see a warning (or an error if using `strict=True`).

!!! note "Write scope required"
    `logfire.variables_push()` and `logfire.variables_push_types()` require an API key with the `project:write_variables` scope.

## Pushing Variable Types

When you have multiple variables that share the same type (e.g., several variables all using the same `AgentConfig` Pydantic model), you can push the type definition itself as a reusable schema. This is done with `logfire.variables_push_types()`.

**Why push variable types?**

- **Schema reuse**: Define a schema once and reference it from multiple variables
- **Centralized management**: Update the schema in one place when your type definition changes
- **Documentation**: Types serve as documentation for the expected structure of variable values

```python skip="true"
from pydantic import BaseModel

import logfire
logfire.configure(
    variables=logfire.VariablesOptions(),
)


class FeatureConfig(BaseModel):
    """Configuration for a feature flag with additional settings."""

    enabled: bool = False
    max_retries: int = 3
    timeout_seconds: float = 30.0


class UserSettings(BaseModel):
    """User preference settings."""

    theme: str = 'light'
    notifications_enabled: bool = True


if __name__ == '__main__':
    # Push type definitions using their class names
    logfire.variables_push_types([FeatureConfig, UserSettings])
```

**Explicit naming:**

By default, types are named using their `__name__` attribute (e.g., `FeatureConfig`). You can provide explicit names using tuples:

```python skip="true"
logfire.variables_push_types([
    (FeatureConfig, 'feature_config'),
    (UserSettings, 'user_settings'),
])
```

**Options:**

| Parameter | Description |
|-----------|-------------|
| `types` | List of types to push. Items can be a type (uses `__name__`) or a tuple of `(type, name)` for explicit naming. |
| `dry_run` | If `True`, shows what would change without actually applying changes. |
| `yes` | If `True`, skips the confirmation prompt. |
| `strict` | If `True`, fails if any existing variable label values are incompatible with the new type schema. |

**Example output:**

```
Variable Types Push Summary
========================================

New types (2):
  + FeatureConfig
  + UserSettings

Apply these changes? [y/N] y

Applying changes...

Done! Variable types synced successfully.
```

When updating existing types, the output shows which types have schema changes:

```
Variable Types Push Summary
========================================

Schema updates (1):
  ~ FeatureConfig

Unchanged (1):
  = UserSettings
```

## Validating Variables

You can validate that your remote variable configurations match your local type definitions using `logfire.variables_validate()`:

```python skip="true"
from logfire.variables import ValidationReport

# Validate all registered variables
report: ValidationReport = logfire.variables_validate()

if report.has_errors:
    print('Validation errors found:')
    print(report.format())
else:
    print('All variables are valid!')

# Check specific issues
if report.variables_not_on_server:
    print(f'Variables missing from server: {report.variables_not_on_server}')
```

The `ValidationReport` provides detailed information about validation results:

| Property | Description |
|----------|-------------|
| `has_errors` | `True` if any validation errors were found |
| `errors` | List of label validation errors with details |
| `variables_checked` | Number of variables that were validated |
| `variables_not_on_server` | Names of local variables not found on the server |
| `description_differences` | Variables where local and server descriptions differ |
| `format()` | Returns a human-readable string of the validation results |

This is useful in CI/CD pipelines to catch configuration drift where someone may have edited a version value in the UI that no longer matches your expected type.

## Config Push Workflow (Programmatic)

For more control over your variable configurations, you can work with config data directly. This workflow allows you to:

- Generate a template config from your code
- Edit the config locally (add rollouts, overrides)
- Push the complete config to Logfire
- Pull existing configs for backup or migration

**Generating a config template:**

```python skip="true"
import json

import logfire
from logfire.variables import VariablesConfig

# Define your variables
agent_config = logfire.var(name='agent_config', type=AgentConfig, default=AgentConfig(...))
feature_flag = logfire.var(name='feature_enabled', type=bool, default=False)

# Build a config with name, schema, and example for each variable
config = logfire.variables_build_config()

# Save to a JSON file
with open('variables.json', 'w', encoding='utf-8') as f:
    f.write(config.model_dump_json(indent=2))
```

The generated file will look like:

```json
{
  "variables": {
    "agent_config": {
      "name": "agent_config",
      "labels": {},
      "latest_version": null,
      "rollout": {"labels": {}},
      "overrides": [],
      "json_schema": {
        "type": "object",
        "properties": {
          "instructions": {"type": "string"},
          "model": {"type": "string"},
          "temperature": {"type": "number"},
          "max_tokens": {"type": "integer"}
        }
      },
      "example": "{\"instructions\":\"You are a helpful assistant.\",\"model\":\"openai:gpt-4o-mini\",\"temperature\":0.7,\"max_tokens\":500}"
    },
    "feature_enabled": {
      "name": "feature_enabled",
      "labels": {},
      "latest_version": null,
      "rollout": {"labels": {}},
      "overrides": [],
      "json_schema": {"type": "boolean"},
      "example": "false"
    }
  }
}
```

**Pushing:**

```python skip="true"
from logfire.variables import VariablesConfig

# Read the edited config
with open('variables.json', 'r', encoding='utf-8') as f:
    config = VariablesConfig.model_validate_json(f.read())

# Sync to the server (metadata only — versions and labels are managed via UI)
logfire.variables_push_config(config)
```

**Push modes:**

| Mode | Description |
|------|-------------|
| `'merge'` (default) | Only create/update variables in the config. Other variables on the server are unchanged. |
| `'replace'` | Make the server match the config exactly. Variables not in the config will be deleted. |

```python skip="true"
# Partial push - only update variables in the config
logfire.variables_push_config(config, mode='merge')

# Full push - delete server variables not in config
logfire.variables_push_config(config, mode='replace')

# Preview changes without applying
logfire.variables_push_config(config, dry_run=True)
```

**Pulling existing config:**

```python skip="true"
# Fetch current config from server
server_config = logfire.variables_pull_config()

# Save for backup or migration
with open('backup.json', 'w', encoding='utf-8') as f:
    f.write(server_config.model_dump_json(indent=2))

# Merge with local changes
merged = server_config.merge(local_config)
```

**VariablesConfig methods:**

| Method | Description |
|--------|-------------|
| `config.merge(other)` | Merge with another config (other takes precedence) |
| `VariablesConfig.from_variables(vars)` | Create minimal config from Variable instances |
