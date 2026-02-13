# Configuration Reference

## Versions, Labels, and Rollouts

**VariableConfig** — Full configuration for a variable:

| Field | Description |
|-------|-------------|
| `name` | Variable name (must match the name in `logfire.var()`) |
| `labels` | Dict of label name to `LabeledValue` or `LabelRef` objects |
| `latest_version` | `LatestVersion` with the most recent version's number and value |
| `rollout` | Default `Rollout` specifying label weights |
| `overrides` | List of `RolloutOverride` for conditional targeting |
| `json_schema` | JSON Schema for validation (optional) |
| `description` | Human-readable description (optional) |
| `aliases` | Alternative names that resolve to this variable (optional, for migrations) |
| `example` | JSON-serialized example value, used as template in UI (optional) |

**LabeledValue** — A label with an inline serialized value:

| Field | Description |
|-------|-------------|
| `version` | The version number this label points to |
| `serialized_value` | JSON-serialized value for this version |

**LabelRef** — A label that references another label, `'latest'`, or `'code_default'`:

| Field | Description |
|-------|-------------|
| `version` | The version number this label points to (optional, can be `None` for label-to-label refs or `code_default`) |
| `ref` | Reference target: another label name, `'latest'`, or `'code_default'` |

Use `LabeledValue` when the label has its own inline value. Use `LabelRef` when the label should follow a reference:

- **Another label name**: Keeps two labels in sync — when the target label is moved, this label follows automatically. Useful when you want e.g. `staging` to always match `production`.
- **`'latest'`**: Always resolves to the most recently created version. This avoids duplicating large values when multiple labels point to the same version.
- **`'code_default'`**: Resolves to `None`, causing the SDK to fall back to the default value defined in code. Useful for disabling remote config for a specific label without removing it.

**LatestVersion** — The most recent version of a variable:

| Field | Description |
|-------|-------------|
| `version` | The version number |
| `serialized_value` | JSON-serialized value |

**Rollout** — Label selection weights:

| Field | Description |
|-------|-------------|
| `labels` | Dict of label name to weight (0.0–1.0). Weights should sum to 1.0 or less. |

If the `labels` dict is empty, all traffic uses the code default (the `default` value passed to `logfire.var()`). If label weights sum to less than 1.0, the remaining percentage uses the code default.

## VariableTypeConfig

**VariableTypeConfig** — Configuration for a reusable type definition:

| Field | Description |
|-------|-------------|
| `name` | Unique name identifying this type |
| `json_schema` | JSON Schema describing the type structure |
| `description` | Human-readable description (optional) |
| `source_hint` | Hint about where this type is defined in code, e.g., `'myapp.config.FeatureConfig'` (optional) |

## Condition Types

Overrides use conditions to match against attributes:

| Condition | Description |
|-----------|-------------|
| `ValueEquals` | Attribute equals a specific value |
| `ValueDoesNotEqual` | Attribute does not equal a specific value |
| `ValueIsIn` | Attribute is in a list of values |
| `ValueIsNotIn` | Attribute is not in a list of values |
| `ValueMatchesRegex` | Attribute matches a regex pattern |
| `ValueDoesNotMatchRegex` | Attribute does not match a regex pattern |
| `KeyIsPresent` | Attribute key exists |
| `KeyIsNotPresent` | Attribute key does not exist |

## Override Example

```python
from logfire.variables.config import (
    KeyIsPresent,
    Rollout,
    RolloutOverride,
    ValueEquals,
    ValueIsIn,
)

overrides = [
    # Beta users in US/UK get the experimental label
    RolloutOverride(
        conditions=[
            ValueEquals(attribute='is_beta', value=True),
            ValueIsIn(attribute='country', values=['US', 'UK']),
        ],
        rollout=Rollout(labels={'experimental': 1.0}),
    ),
    # Anyone with a custom config attribute gets the custom label
    RolloutOverride(
        conditions=[KeyIsPresent(attribute='custom_config')],
        rollout=Rollout(labels={'custom': 1.0}),
    ),
]
```

Conditions within an override are AND-ed together. Overrides are evaluated in order; the first matching override's rollout is used.

## Advanced Usage

### Contextual Overrides

Use `variable.override()` to temporarily override a variable's value within a context. This is useful for testing:

```python skip="true"
def test_premium_config_handling():
    """Test that premium configuration works correctly."""
    premium_config = AgentConfig(
        instructions='Premium instructions...',
        model='openai:gpt-4o',
        temperature=0.3,
        max_tokens=1000,
    )

    with agent_config.override(premium_config):
        # Inside this context, agent_config.get() returns premium_config
        with agent_config.get() as config:
            assert config.value.model == 'openai:gpt-4o'

    # Back to normal after context exits
```

### Dynamic Override Functions

Override with a function that computes the value based on context:

```python skip="true"
from collections.abc import Mapping
from typing import Any


def get_config_for_context(
    targeting_key: str | None, attributes: Mapping[str, Any] | None
) -> AgentConfig:
    """Compute configuration based on context."""
    if attributes and attributes.get('mode') == 'creative':
        return AgentConfig(
            instructions='Be creative and expressive...',
            model='openai:gpt-4o',
            temperature=1.0,
            max_tokens=1000,
        )
    return AgentConfig(
        instructions='Be precise and factual...',
        model='openai:gpt-4o-mini',
        temperature=0.2,
        max_tokens=500,
    )


with agent_config.override(get_config_for_context):
    # Configuration will be computed based on the attributes passed to get()
    with agent_config.get(attributes={'mode': 'creative'}) as config:
        assert config.value.temperature == 1.0
```

### Refreshing Variables

Variables are automatically refreshed in the background when using the remote provider. You can also manually trigger a refresh:

```python skip="true"
# Synchronous refresh
agent_config.refresh_sync(force=True)

# Async refresh
await agent_config.refresh(force=True)
```

The `force=True` parameter bypasses the polling interval check and fetches the latest configuration immediately.

### Migrating Variable Names

Variable names serve as the identifier used to reference the variable in your code. You can rename a variable in the UI or API, but any deployed code still using the old name will fall back to its code default. For zero-downtime migrations, use **aliases**.

Aliases allow a variable to be found by alternative names. When your code requests a variable by name, if that name isn't found directly, the system checks if it matches any alias of an existing variable and returns that variable's value instead.

**Migration workflow:**

1. **Create the new variable** with your desired name and copy the configuration (versions, labels, rollouts, overrides) from the old variable
2. **Add the old name as an alias** on the new variable
3. **Update your code** to use the new variable name
4. **Deploy gradually**: Applications using the old name will still work because the alias resolves to the new variable
5. **Delete the old variable** once all code has been updated and deployed
6. **Remove the alias** (optional) once you're confident no code uses the old name

**Example:**

Suppose you have a variable named `agent_config` and want to rename it to `support_agent_config`:

1. Create `support_agent_config` with the same versions, labels, and rollout configuration
2. Add `agent_config` as an alias on `support_agent_config`
3. Old code using `logfire.var(name='agent_config', ...)` continues to work
4. Update your code to use `name='support_agent_config'`
5. After deployment, delete the old `agent_config` variable
6. Optionally remove `agent_config` from the aliases list

This approach ensures zero-downtime migrations. Existing deployed applications continue to receive the correct configuration while you update and redeploy.

**In the UI:**

You can manage aliases in the **Aliases** section of the **Settings** tab on the variable detail page. Add the old variable name(s) that should resolve to this variable.

**In code (local config):**

```python skip="true"
from logfire.variables.config import VariableConfig, VariablesConfig

config = VariablesConfig(
    variables={
        'support_agent_config': VariableConfig(
            name='support_agent_config',
            labels={...},
            latest_version=LatestVersion(...),
            rollout=Rollout(labels={...}),
            overrides=[],
            # Old name resolves to this variable
            aliases=['agent_config'],
        ),
    }
)
```

[slack]: https://logfire.pydantic.dev/docs/join-slack/
