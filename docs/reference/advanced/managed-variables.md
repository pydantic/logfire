# Managed Variables

Managed variables let you define and reference configuration in your code, but control the runtime values from the Logfire UI without redeploying.

Define a variable once with a sensible default, deploy your application, then iterate on the values in production. You can target specific populations (opted-in beta users, internal developers, enterprise customers, etc.) using flexible targeting rules that integrate with your existing OpenTelemetry attributes.

Changes take effect quickly, and every variable resolution is visible in your traces. This trace-level visibility means you can correlate application behavior directly with configuration variants, enabling A/B testing, automated prompt optimization, and online evaluations using the same observability data you're already sending to Logfire.

## What Are Managed Variables?

Managed variables are a way to externalize runtime configuration from your code. While they're especially powerful for AI applications (where prompt iteration is frequently critical), they work for any configuration you want to change without redeploying:

- **Any type**: Use primitives (strings, bools, ints) or structured types (dataclasses, Pydantic models, etc.)
- **Observability-integrated**: Every variable resolution creates a span, and using the context manager automatically sets baggage so downstream operations are tagged with which variant was used
- **Variants and rollouts**: Define multiple values (variants) for a variable and control what percentage of requests get each variant
- **Targeting**: Route specific users or segments to specific variants based on attributes

## Structured Configuration

While you can use simple primitive types as variables, the real power comes from using **structured types**—Pydantic models that group related configuration together:

```python
from pydantic import BaseModel

import logfire

logfire.configure()


class AgentConfig(BaseModel):
    """Configuration for an AI agent."""

    instructions: str
    model: str
    temperature: float
    max_tokens: int


# Create a managed variable with this structured type
agent_config = logfire.var(
    name='agent-config',
    type=AgentConfig,
    default=AgentConfig(
        instructions='You are a helpful assistant.',
        model='openai:gpt-4o-mini',
        temperature=0.7,
        max_tokens=500,
    ),
)
```

**Why group configuration together instead of using separate variables?**

- **Coherent variants**: A variant isn't just "instructions v2", it's a complete configuration where all the pieces work well together. The temperature that works with a detailed prompt might not work as well with a concise one.
- **Atomic changes**: When you roll out a new variant, all settings change together. No risk of mismatched configurations.
- **Holistic A/B testing**: Compare "config v1" vs "config v2" as complete packages, not individual parameters in isolation.
- **Simpler management**: One variable to manage in the UI instead of many.

!!! tip "When to use primitives"
    Simple standalone settings like feature flags (`debug_mode: bool`), rate limits (`max_requests: int`), or even just agent instructions work great as primitive variables. Use structured types when you have multiple settings you want to vary together.

## Why This Is So Useful For AI Applications

In AI applications, prompts and model configurations are often critical to application behavior. Some changes are minor tweaks that don't significantly affect outputs, while others can have substantial positive or negative consequences. The traditional iteration process looks like:

1. Edit the code
2. Open a PR and get it reviewed
3. Merge and deploy
4. Wait to see the effect in production

This process is problematic for AI configuration because:

- **Production data is essential**: Useful AI agents often need access to production data and real user interactions. Testing locally or in staging environments rarely captures the full range of inputs your application will encounter.
- **Representative testing is hard**: Even a fast deployment cycle adds significant friction when you're iterating on prompts. What works in a test environment may behave differently with real user queries.
- **Risk affects all users**: Without targeting controls, every change affects your entire user base immediately.

With managed variables, you can iterate safely in production:

- **Iteration speed**: Edit prompts in the Logfire UI and see the effect in real traces immediately
- **A/B testing**: Run multiple prompt/model/temperature combinations simultaneously and compare their performance in your traces
- **Gradual rollouts**: Start a new configuration at 5% of traffic, watch the metrics, then gradually increase
- **Emergency rollback**: If a configuration is causing problems, revert to the previous variant in seconds, with no deploy required

## How It Works

Here's the typical workflow using the `AgentConfig` example from above:

1. **Define the variable in code** with your current configuration as the default
2. **Deploy your application**: it starts using the default immediately
3. **Push your variable schema** to Logfire using `logfire.push_variables()` (this makes it easier to create new variants in the UI with the correct structure)
4. **Create variants in the Logfire UI**: for example, a "v2-detailed" variant with longer instructions and lower temperature
5. **Set up a rollout**: start with 10% of traffic going to the new variant
6. **Monitor in real-time**: filter traces by variant to compare response quality, latency, and token usage
7. **Adjust based on data**: if v2 performs better, gradually increase to 50%, then 100%
8. **Iterate**: create new variants, adjust rollouts, all without code changes

In the Logfire UI, you can:

- Create new variants for any variable with different values
- Set rollout percentages (e.g., 80% variant A, 20% variant B)
- Define targeting rules (e.g., enterprise users always get variant A)
- See which variants are being served in real-time
- Filter and group traces by variant to compare performance

## Quick Start

### Define a Variable

Use `logfire.var()` to define a managed variable. Here's an example using a structured configuration:

```python
from pydantic import BaseModel

import logfire

logfire.configure()


class AgentConfig(BaseModel):
    """Configuration for a customer support agent."""

    instructions: str
    model: str
    temperature: float
    max_tokens: int


# Define the variable with a sensible default
agent_config = logfire.var(
    name='support-agent-config',
    type=AgentConfig,
    default=AgentConfig(
        instructions='You are a helpful customer support agent. Be friendly and concise.',
        model='openai:gpt-4o-mini',
        temperature=0.7,
        max_tokens=500,
    ),
)
```

### Use the Variable

The recommended pattern is to use the variable's `.get()` method as a context manager. This automatically:

- Creates a span for the variable resolution
- Sets baggage with the variable name and selected variant

When using the Logfire SDK, baggage values are automatically added as attributes to all downstream spans. This means any spans created inside the context manager will be tagged with which variant was used, making it easy to filter and compare behavior by variant in the Logfire UI.

```python
from pydantic_ai import Agent


async def handle_support_ticket(user_id: str, message: str) -> str:
    """Handle a customer support request."""
    # Get the configuration - same user always gets the same variant
    with agent_config.get(targeting_key=user_id) as config:
        # Inside this context, baggage is set:
        # logfire.variables.support-agent-config = <variant_name>

        agent = Agent(
            config.value.model,
            system_prompt=config.value.instructions,
        )
        result = await agent.run(
            message,
            model_settings={
                'temperature': config.value.temperature,
                'max_tokens': config.value.max_tokens,
            },
        )
        return result.output
```

The `targeting_key` ensures deterministic variant selection: the same user always gets the same variant, which is essential for application behavior consistency when A/B testing.

In practice, depending on your application structure, you may want to use `tenant_id` or another identifier for `targeting_key` instead of `user_id`. If no `targeting_key` is provided and there's an active trace, the `trace_id` is used automatically to ensure consistent behavior within a single request.

### Variable Parameters

| Parameter | Description                                                             |
|-----------|-------------------------------------------------------------------------|
| `name` | Unique identifier for the variable                                      |
| `type` | Expected type for validation; can be a primitive type or Pydantic model |
| `default` | Default value when no configuration is found (can also be a function)   |

## A/B Testing Configurations

Here's a complete example showing how to A/B test two complete agent configurations:

```python
from pydantic import BaseModel
from pydantic_ai import Agent

import logfire
from logfire.variables.config import (
    Rollout,
    VariableConfig,
    VariablesConfig,
    Variant,
)

logfire.configure()


class AgentConfig(BaseModel):
    """Configuration for a customer support agent."""

    instructions: str
    model: str
    temperature: float
    max_tokens: int


# For local development/testing, you can define variants in code
# In production, you'd typically configure these in the Logfire UI
# and configure logfire to retrieve and sync with the remotely-managed config.
variables_config = VariablesConfig(
    variables={
        'support-agent-config': VariableConfig(
            name='support-agent-config',
            variants={
                'v1-concise': Variant(
                    key='v1-concise',
                    serialized_value="""{
                        "instructions": "You are a helpful support agent. Be brief and direct.",
                        "model": "openai:gpt-4o-mini",
                        "temperature": 0.7,
                        "max_tokens": 300
                    }""",
                    description='Concise responses with faster model',
                ),
                'v2-detailed': Variant(
                    key='v2-detailed',
                    serialized_value="""{
                        "instructions": "You are an expert support agent. Provide thorough explanations with examples. Always acknowledge the customer's concern before providing assistance.",
                        "model": "openai:gpt-4o",
                        "temperature": 0.3,
                        "max_tokens": 800
                    }""",
                    description='Detailed responses with more capable model',
                ),
            },
            # 50/50 A/B test
            rollout=Rollout(variants={'v1-concise': 0.5, 'v2-detailed': 0.5}),
            overrides=[],
            json_schema={
                'type': 'object',
                'properties': {
                    'instructions': {'type': 'string'},
                    'model': {'type': 'string'},
                    'temperature': {'type': 'number'},
                    'max_tokens': {'type': 'integer'},
                },
            },
        ),
    }
)

logfire.configure(
    variables=logfire.VariablesOptions(config=variables_config),
)

# Define the variable
agent_config = logfire.var(
    name='support-agent-config',
    type=AgentConfig,
    default=AgentConfig(
        instructions='You are a helpful assistant.',
        model='openai:gpt-4o-mini',
        temperature=0.7,
        max_tokens=500,
    ),
)


async def handle_ticket(user_id: str, message: str) -> str:
    """Handle a support ticket with A/B tested configuration."""
    with agent_config.get(targeting_key=user_id) as config:
        # The variant (v1-concise or v2-detailed) is now in baggage
        # All spans created below, including those from the call to agent.run, will be tagged with the variant

        agent = Agent(config.value.model, system_prompt=config.value.instructions)
        result = await agent.run(
            message,
            model_settings={
                'temperature': config.value.temperature,
                'max_tokens': config.value.max_tokens,
            },
        )
        return result.output
```

**Analyzing the A/B test in Logfire:**

After running traffic through both variants, you can:

1. Filter traces by the variant baggage to see only requests that used a specific variant
2. Compare metrics like response latency, token usage, and error rates between variants
3. Look at actual responses to qualitatively assess which variant performs better
4. Make data-driven decisions about which configuration to roll out to 100%

## Targeting Users and Segments

### Targeting Key

The `targeting_key` parameter ensures deterministic variant selection. The same key always produces the same variant, which is useful for:

- **Consistent user experience**: You typically want users to see consistent configuration behavior within a session, or even across sessions. You may also want all users within a single tenant to receive the same variant.
- **Debugging**: By controlling the `targeting_key`, you can deterministically get the same configuration variant that a user received. Note that this reproduces the *configuration*, not the exact behavior; if your application includes stochastic elements like LLM calls, outputs will still vary.

```python
# User-based targeting
with agent_config.get(targeting_key=user_id) as config:
    ...

# Request-based targeting (if no targeting_key provided and there's an active trace,
# the trace ID is used automatically)
with agent_config.get() as config:
    ...
```

### Attributes for Conditional Rules

Pass attributes to enable condition-based targeting:

```python
with agent_config.get(
    targeting_key=user_id,
    attributes={
        'plan': 'enterprise',
        'region': 'us-east',
        'is_beta_user': True,
    },
) as config:
    ...
```

These attributes can be used in override rules to route specific segments to specific variants:

```python
from logfire.variables.config import (
    Rollout,
    RolloutOverride,
    ValueEquals,
    VariableConfig,
    VariablesConfig,
    Variant,
)

variables_config = VariablesConfig(
    variables={
        'support-agent-config': VariableConfig(
            name='support-agent-config',
            variants={
                'standard': Variant(
                    key='standard',
                    serialized_value='{"instructions": "Be helpful and concise.", ...}',
                ),
                'premium': Variant(
                    key='premium',
                    serialized_value='{"instructions": "Provide detailed, thorough responses...", ...}',
                ),
            },
            # Default: everyone gets 'standard'
            rollout=Rollout(variants={'standard': 1.0}),
            overrides=[
                # Enterprise plan users always get the premium variant
                RolloutOverride(
                    conditions=[ValueEquals(attribute='plan', value='enterprise')],
                    rollout=Rollout(variants={'premium': 1.0}),
                ),
            ],
            json_schema={'type': 'object'},
        ),
    }
)

# Now when you call get() with attributes:
with agent_config.get(
    targeting_key=user_id,
    attributes={'plan': 'enterprise'},  # Matches the override condition
) as config:
    # config.variant will be 'premium' because of the override
    ...

with agent_config.get(
    targeting_key=user_id,
    attributes={'plan': 'free'},  # Does not match override
) as config:
    # config.variant will be 'standard' (the default rollout)
    ...
```

### Automatic Context Enrichment

By default, Logfire automatically includes additional context when resolving variables:

- **Resource attributes**: OpenTelemetry resource attributes (service name, version, environment)
- **Baggage**: Values set via `logfire.set_baggage()`

This means your targeting rules can match against service identity or request-scoped baggage without explicitly passing them.

**Example: Plan-based targeting with baggage**

If your application sets the user's plan as baggage early in the request lifecycle, you can use it for targeting without passing it explicitly to every variable resolution:

```python
# In your middleware or request handler, set the plan once
with logfire.set_baggage(plan='enterprise'):
    # ... later in your application code ...
    with agent_config.get(targeting_key=user_id) as config:
        # The variable resolution automatically sees plan='enterprise'
        # If you have an override targeting enterprise users, it will match
        ...
```

This is useful when you want different configurations based on user plan—for example, enterprise users might get a prompt variant that references tools only available to them.

**Example: Environment-based targeting with resource attributes**

Resource attributes like `deployment.environment` are automatically included, allowing you to use different configurations in different environments without code changes:

- Use a more experimental prompt on staging to test changes before production
- Enable verbose logging in development but not in production
- Route all staging traffic to a "debug" variant that includes extra context

To disable automatic context enrichment:

```python
logfire.configure(
    variables=logfire.VariablesOptions(
        include_resource_attributes_in_context=False,
        include_baggage_in_context=False,
    ),
)
```

## Remote Variables

When connected to Logfire, variables are managed through the Logfire UI. This is the recommended setup for production.

To enable remote variables, you need to explicitly opt in using `VariablesOptions`:

```python
import logfire
from logfire.variables.config import RemoteVariablesConfig

# Enable remote variables
logfire.configure(
    variables=logfire.VariablesOptions(
        config=RemoteVariablesConfig(),
    ),
)

# Define your variables
agent_config = logfire.var(
    name='support-agent-config',
    type=AgentConfig,
    default=AgentConfig(...),
)
```

!!! note "API Token Required"
    Remote variables require an API token with the `project:read_variables` scope. This is different from the write token (`LOGFIRE_TOKEN`) used to send traces and logs. Set it via the `LOGFIRE_API_TOKEN` environment variable or pass it directly to `RemoteVariablesConfig(api_token=...)`.

**How remote variables work:**

1. Your application connects to Logfire using your API token
2. Variable configurations are fetched from the Logfire API
3. A background thread polls for updates (default: every 30 seconds)
4. When you change a variant or rollout in the UI, running applications pick up the change automatically while polling

**Configuration options:**

```python
from datetime import timedelta

from logfire.variables.config import RemoteVariablesConfig

logfire.configure(
    variables=logfire.VariablesOptions(
        config=RemoteVariablesConfig(
            # Block until first fetch completes (default: True)
            # Set to False if you want the app to start immediately using defaults
            block_before_first_resolve=True,
            # How often to poll for updates (default: 30 seconds)
            polling_interval=timedelta(seconds=30),
        ),
    ),
)
```

## Local Variables

For development, testing, or self-hosted deployments, you can configure variables locally using `VariablesConfig`:

```python
import logfire
from logfire.variables.config import (
    Rollout,
    RolloutOverride,
    ValueEquals,
    VariableConfig,
    VariablesConfig,
    Variant,
)

variables_config = VariablesConfig(
    variables={
        'support-agent-config': VariableConfig(
            name='support-agent-config',
            variants={
                'default': Variant(
                    key='default',
                    serialized_value='{"instructions": "...", "model": "...", "temperature": 0.7, "max_tokens": 500}',
                ),
                'premium': Variant(
                    key='premium',
                    serialized_value='{"instructions": "...", "model": "...", "temperature": 0.3, "max_tokens": 1000}',
                ),
            },
            # Default: everyone gets 'default'
            rollout=Rollout(variants={'default': 1.0}),
            overrides=[
                # Enterprise users get 'premium'
                RolloutOverride(
                    conditions=[ValueEquals(attribute='plan', value='enterprise')],
                    rollout=Rollout(variants={'premium': 1.0}),
                ),
            ],
            json_schema={'type': 'object'},
        ),
    }
)

logfire.configure(
    variables=logfire.VariablesOptions(config=variables_config),
)
```

**When to use local variables:**

- **Development**: Test different configurations without connecting to Logfire
- **Testing**: Use fixed configurations in your test suite
- **Self-hosted**: Full control over variable configuration without external dependencies
- **Optimization harnesses**: Build automated optimization loops that monitor performance metrics and programmatically update variable values

The local provider exposes methods to create, update, and delete variables and variants programmatically. This makes it possible to build optimization harnesses that:

1. Run your application with different configurations
2. Collect performance metrics from traces
3. Use the metrics to decide on new configurations to try
4. Update variable values via the local provider's API
5. Repeat until optimal configuration is found

This workflow is particularly useful for automated prompt optimization, where you want to systematically explore different prompt variations and measure their effectiveness.

## Configuration Reference

### Variants and Rollouts

**VariableConfig** - Full configuration for a variable:

| Field | Description |
|-------|-------------|
| `name` | Variable name (must match the name in `logfire.var()`) |
| `variants` | Dict of variant key to `Variant` objects |
| `rollout` | Default `Rollout` specifying variant weights |
| `overrides` | List of `RolloutOverride` for conditional targeting |
| `json_schema` | JSON Schema for validation (optional) |
| `description` | Human-readable description (optional) |

**Variant** - A single variant value:

| Field | Description |
|-------|-------------|
| `key` | Unique identifier for this variant |
| `serialized_value` | JSON-serialized value |
| `description` | Human-readable description (optional) |

**Rollout** - Variant selection weights:

| Field | Description |
|-------|-------------|
| `variants` | Dict of variant key to weight (0.0-1.0). Weights should sum to 1.0 or less. |

If weights sum to less than 1.0, there's a chance no variant is selected and the code default is used.

### Condition Types

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

### Override Example

```python
from logfire.variables.config import (
    KeyIsPresent,
    Rollout,
    RolloutOverride,
    ValueEquals,
    ValueIsIn,
)

overrides = [
    # Beta users in US/UK get the experimental variant
    RolloutOverride(
        conditions=[
            ValueEquals(attribute='is_beta', value=True),
            ValueIsIn(attribute='country', values=['US', 'UK']),
        ],
        rollout=Rollout(variants={'experimental': 1.0}),
    ),
    # Anyone with a custom config attribute gets the custom variant
    RolloutOverride(
        conditions=[KeyIsPresent(attribute='custom_config')],
        rollout=Rollout(variants={'custom': 1.0}),
    ),
]
```

Conditions within an override are AND-ed together. Overrides are evaluated in order; the first matching override's rollout is used.

## Advanced Usage

### Contextual Overrides

Use `variable.override()` to temporarily override a variable's value within a context. This is useful for testing:

```python
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

```python
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

```python
# Synchronous refresh
agent_config.refresh_sync(force=True)

# Async refresh
await agent_config.refresh(force=True)
```

The `force=True` parameter bypasses the polling interval check and fetches the latest configuration immediately.
