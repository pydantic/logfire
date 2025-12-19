# Managed Variables

Managed variables provide a way to dynamically configure values in your application—such as LLM prompts, model parameters, feature flags, and more—without redeploying code. They're particularly useful for AI applications where you want to iterate on prompts, adjust model settings, or run A/B tests.

## Why Use Managed Variables?

### LLM Prompt Management

When building AI applications, you often need to:

- **Iterate on prompts quickly** without code changes or deployments
- **A/B test different prompts** to find what works best
- **Manage model parameters** like temperature, max tokens, or model selection
- **Roll out prompt changes gradually** to a subset of users

### Beyond AI: Traditional Feature Flags

Managed variables also work great for traditional use cases:

- Feature flags and gradual rollouts
- Configuration that varies by environment or user segment
- Runtime-adjustable settings without restarts

## Basic Usage

### Creating a Variable

Use `logfire.var()` to create a managed variable:

```python
import logfire

logfire.configure()

# Define a variable for your AI agent's system prompt
agent_instructions = logfire.var(
    name='agent_instructions',
    default='You are a helpful assistant.',
    type=str,
)


async def main():
    # Get the variable's resolution details and use as context manager
    with await agent_instructions.get() as details:
        print(f'Instructions: {details.value}')
        #> Instructions: You are a helpful assistant.
```

### Variable Parameters

| Parameter | Description |
|-----------|-------------|
| `name` | Unique identifier for the variable |
| `default` | Default value when no configuration is found (can also be a function) |
| `type` | Expected type(s) for validation — can be a single type or sequence of types |

### Getting Variable Values

Variables' `.get()` method returns a `ResolvedVariable` object containing the resolved value and metadata about how it was resolved:

```python
import logfire

logfire.configure()

my_variable = logfire.var(
    name='my_variable',
    default='default value',
    type=str,
)


async def main():
    # Get full resolution details (includes variant info, any errors, etc.)
    details = await my_variable.get()
    print(f'Resolved value: {details.value}')
    #> Resolved value: default value
    print(f'Selected variant: {details.variant}')
    #> Selected variant: None
```

### Using Variables as Context Managers (Recommended)

The `ResolvedVariable` object can be used as a context manager. This is the **recommended pattern** because it automatically sets [baggage](baggage.md) with the variable name and selected variant, allowing downstream spans and logs to be associated with the variable resolution:

```python
import logfire

logfire.configure()

system_prompt = logfire.var(
    name='system_prompt',
    default='You are a helpful assistant.',
    type=str,
)


async def main():
    # Use as context manager to automatically track the variable variant
    with await system_prompt.get() as details:
        prompt = details.value
        # Inside this context, baggage is automatically set:
        # logfire.variables.system_prompt = <variant_name>
        # Any spans or logs created here will have this baggage attached,
        # making it easy to correlate behavior with the variant that was used.
        print(f'Using prompt variant: {details.variant}')
        # ... use the prompt value for your AI agent or other logic ...
```

This pattern is especially useful for:

- **A/B testing analysis**: Easily filter traces by which variant was active
- **Debugging**: Understand which configuration was in effect during a request
- **Observability**: Track how different variants affect application behavior

### Targeting and Attributes

You can pass targeting information to influence which variant is selected:

```python
import logfire

logfire.configure()

agent_instructions = logfire.var(
    name='agent_instructions',
    default='You are a helpful assistant.',
    type=str,
)


async def main():
    # Target a specific user for consistent A/B test assignment
    with await agent_instructions.get(
        targeting_key='user_123',  # Used for deterministic variant selection
        attributes={'plan': 'enterprise', 'region': 'us-east'},
    ) as details:
        print(details.value)
        #> You are a helpful assistant.
```

The `targeting_key` ensures the same user always gets the same variant (deterministic selection based on the key). Additional `attributes` can be used for condition-based targeting rules.

!!! note "Automatic Context Enrichment"
    By default, Logfire automatically merges OpenTelemetry resource attributes and [baggage](baggage.md) into the attributes used for variable resolution. This means your targeting rules can match against service name, environment, or request-scoped baggage without explicitly passing them. See [Automatic Context Enrichment](#automatic-context-enrichment) for details and how to disable this behavior.

## Contextual Overrides

Use `variable.override()` to temporarily override a variable's value within a context. This is useful for testing or for request-scoped customization:

```python
import logfire

logfire.configure()

model_temperature = logfire.var(
    name='model_temperature',
    default=0.7,
    type=float,
)


async def main():
    # Default value
    details = await model_temperature.get()
    print(f'Default temperature: {details.value}')
    #> Default temperature: 0.7

    # Override for creative mode
    with model_temperature.override(1.0):
        details = await model_temperature.get()
        print(f'Creative temperature: {details.value}')
        #> Creative temperature: 1.0

    # Back to default after context exits
    details = await model_temperature.get()
    print(f'Back to default: {details.value}')
    #> Back to default: 0.7
```

### Dynamic Override Functions

You can also override with a function that computes the value dynamically based on the targeting key and attributes:

```python
from collections.abc import Mapping
from typing import Any

import logfire

logfire.configure()

model_temperature = logfire.var(
    name='model_temperature',
    default=0.7,
    type=float,
)


def get_temperature_for_context(
    targeting_key: str | None, attributes: Mapping[str, Any] | None
) -> float:
    """Compute temperature based on context."""
    if attributes and attributes.get('mode') == 'creative':
        return 1.0
    return 0.5


async def main():
    with model_temperature.override(get_temperature_for_context):
        # Temperature will be computed based on the attributes passed to get()
        details = await model_temperature.get(attributes={'mode': 'creative'})
        print(f'Creative mode: {details.value}')
        #> Creative mode: 1.0

        details = await model_temperature.get(attributes={'mode': 'precise'})
        print(f'Precise mode: {details.value}')
        #> Precise mode: 0.5
```

## Local Variable Provider

The `LogfireLocalProvider` lets you configure variables from a local configuration object. This is useful for development, testing, or self-hosted deployments where you want full control over variable values.

### Configuration Structure

Variables are configured using `VariablesConfig`, which defines:

- **Variables**: Each variable has variants (possible values) and rollout rules
- **Variants**: Named values that can be selected
- **Rollouts**: Probability weights for selecting variants
- **Overrides**: Conditional rules that change the rollout based on attributes

### Example: Configuring a PydanticAI Agent

Here's a complete example that configures system prompts for a [PydanticAI](https://ai.pydantic.dev/) agent with A/B testing and user-based targeting:

```python
import logfire
from pydantic_ai import Agent

from logfire.variables.config import (
    Rollout,
    RolloutOverride,
    VariableConfig,
    VariablesConfig,
    Variant,
    ValueEquals,
)

# Define variable configurations
variables_config = VariablesConfig(
    variables={
        'assistant_system_prompt': VariableConfig(
            name='assistant_system_prompt',
            variants={
                'default': Variant(
                    key='default',
                    serialized_value='"You are a helpful AI assistant."',
                ),
                'detailed': Variant(
                    key='detailed',
                    serialized_value='"You are a helpful AI assistant. Always provide detailed explanations with examples. Structure your responses with clear headings."',
                ),
                'concise': Variant(
                    key='concise',
                    serialized_value='"You are a helpful AI assistant. Be brief and direct. Avoid unnecessary elaboration."',
                ),
            },
            # Default rollout: 80% default, 10% detailed, 10% concise
            rollout=Rollout(variants={'default': 0.8, 'detailed': 0.1, 'concise': 0.1}),
            overrides=[
                # Enterprise users always get the detailed prompt
                RolloutOverride(
                    conditions=[ValueEquals(attribute='plan', value='enterprise')],
                    rollout=Rollout(variants={'detailed': 1.0}),
                ),
            ],
            json_schema={'type': 'string'},
        ),
    }
)

# Configure Logfire with the local provider
logfire.configure(
    variables=logfire.VariablesOptions(provider=variables_config),
)
logfire.instrument_pydantic_ai()

# Define the variable
system_prompt = logfire.var(
    name='assistant_system_prompt',
    default='You are a helpful assistant.',
    type=str,
)


async def run_agent(user_id: str, user_plan: str, user_message: str) -> str:
    """Run the agent with the appropriate prompt for this user."""
    # Get the prompt - variant selection is deterministic per user
    # Using the context manager ensures the variant is recorded in baggage
    with await system_prompt.get(
        targeting_key=user_id,
        attributes={'plan': user_plan},
    ) as details:
        # Create the agent with the resolved prompt
        agent = Agent('openai:gpt-4o-mini', system_prompt=details.value)
        result = await agent.run(user_message)
        return result.output


async def main():
    # Enterprise user gets the detailed prompt
    response = await run_agent(
        user_id='enterprise_user_1',
        user_plan='enterprise',
        user_message='What is Python?',
    )
    print(f'Enterprise user response: {response}')

    # Free user gets one of the default rollout variants
    response = await run_agent(
        user_id='free_user_42',
        user_plan='free',
        user_message='What is Python?',
    )
    print(f'Free user response: {response}')
```

### Variant Selection

Variants are selected based on:

1. **Overrides**: Conditions are evaluated in order; the first matching override's rollout is used
2. **Rollout weights**: Variants are selected probabilistically based on their weights
3. **Targeting key**: When provided, ensures consistent selection for the same key (useful for A/B tests)

If rollout weights sum to less than 1.0, there's a chance no variant is selected and the code default is used.

## Rollout Schedules

Rollout schedules enable time-based progression through multiple rollout stages, allowing for gradual rollouts where variant selection weights change over time. This is useful for:

- **Canary deployments**: Start with a small percentage of traffic, then gradually increase
- **Phased feature launches**: Roll out new features to more users over time
- **Time-limited experiments**: Run A/B tests for specific durations

### How Schedules Work

A schedule has a `start_at` time and a list of stages. Each stage has:

- **duration**: How long to remain in this stage
- **rollout**: The variant selection weights for this stage
- **overrides**: Optional conditional rules specific to this stage

The schedule progresses through stages sequentially. When the current time is:

- Before `start_at`: Uses the base rollout and overrides
- Within a stage's duration: Uses that stage's rollout and overrides
- After all stages complete: Returns to the base rollout and overrides

### Example: Gradual Rollout

Here's an example of a three-stage canary deployment:

```python
from datetime import datetime, timedelta, timezone

from logfire.variables.config import (
    Rollout,
    RolloutSchedule,
    RolloutStage,
    VariableConfig,
    Variant,
)

# Schedule a gradual rollout starting now
config = VariableConfig(
    name='new_feature_enabled',
    variants={
        'disabled': Variant(key='disabled', serialized_value='false'),
        'enabled': Variant(key='enabled', serialized_value='true'),
    },
    # Base rollout: feature disabled (used before/after schedule)
    rollout=Rollout(variants={'disabled': 1.0}),
    overrides=[],
    schedule=RolloutSchedule(
        start_at=datetime.now(timezone.utc),
        stages=[
            # Stage 1: Canary - 5% for 1 hour
            RolloutStage(
                duration=timedelta(hours=1),
                rollout=Rollout(variants={'disabled': 0.95, 'enabled': 0.05}),
                overrides=[],
            ),
            # Stage 2: Early adopters - 25% for 4 hours
            RolloutStage(
                duration=timedelta(hours=4),
                rollout=Rollout(variants={'disabled': 0.75, 'enabled': 0.25}),
                overrides=[],
            ),
            # Stage 3: Full rollout - 100% for 24 hours
            RolloutStage(
                duration=timedelta(hours=24),
                rollout=Rollout(variants={'enabled': 1.0}),
                overrides=[],
            ),
        ],
    ),
)
```

### Stage-Specific Overrides

Each stage can have its own conditional overrides, allowing different targeting rules at different stages:

```python
from datetime import datetime, timedelta, timezone

from logfire.variables.config import (
    Rollout,
    RolloutOverride,
    RolloutSchedule,
    RolloutStage,
    ValueEquals,
    VariableConfig,
    Variant,
)

config = VariableConfig(
    name='new_prompt',
    variants={
        'old': Variant(key='old', serialized_value='"Old prompt"'),
        'new': Variant(key='new', serialized_value='"New prompt"'),
    },
    rollout=Rollout(variants={'old': 1.0}),
    overrides=[],
    schedule=RolloutSchedule(
        start_at=datetime.now(timezone.utc),
        stages=[
            # Stage 1: Only beta users get the new prompt
            RolloutStage(
                duration=timedelta(hours=2),
                rollout=Rollout(variants={'old': 1.0}),
                overrides=[
                    RolloutOverride(
                        conditions=[ValueEquals(attribute='is_beta', value=True)],
                        rollout=Rollout(variants={'new': 1.0}),
                    ),
                ],
            ),
            # Stage 2: Beta users and enterprise users
            RolloutStage(
                duration=timedelta(hours=4),
                rollout=Rollout(variants={'old': 1.0}),
                overrides=[
                    RolloutOverride(
                        conditions=[ValueEquals(attribute='is_beta', value=True)],
                        rollout=Rollout(variants={'new': 1.0}),
                    ),
                    RolloutOverride(
                        conditions=[ValueEquals(attribute='plan', value='enterprise')],
                        rollout=Rollout(variants={'new': 1.0}),
                    ),
                ],
            ),
            # Stage 3: Everyone gets the new prompt
            RolloutStage(
                duration=timedelta(hours=24),
                rollout=Rollout(variants={'new': 1.0}),
                overrides=[],
            ),
        ],
    ),
)
```

### Schedule Lifecycle

!!! note "Local vs. Server-Side Schedules"
    When using the local provider, schedules are evaluated client-side based on the current time. This means:

    - The schedule progresses automatically as time passes
    - After the schedule completes, the base rollout is used again
    - To make the final stage permanent, update the configuration to set the base rollout to the desired final state

    Server-side schedule management (with automated rollback based on error rates) will be available with the remote provider in a future release.

## Condition Types

Overrides use conditions to match against the provided attributes. Available condition types:

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

### Example: Complex Targeting Rules

```python
from logfire.variables.config import (
    KeyIsPresent,
    Rollout,
    RolloutOverride,
    ValueEquals,
    ValueIsIn,
)

overrides = [
    # Beta users in US/UK get the experimental prompt
    RolloutOverride(
        conditions=[
            ValueEquals(attribute='is_beta', value=True),
            ValueIsIn(attribute='country', values=['US', 'UK']),
        ],
        rollout=Rollout(variants={'experimental': 1.0}),
    ),
    # Anyone with a custom_prompt attribute gets it used
    RolloutOverride(
        conditions=[KeyIsPresent(attribute='custom_prompt')],
        rollout=Rollout(variants={'custom': 1.0}),
    ),
]
```

## Automatic Context Enrichment

By default, Logfire automatically includes additional context when resolving variables:

- **Resource attributes**: OpenTelemetry resource attributes (service name, version, etc.)
- **Baggage**: Values set via `logfire.set_baggage()`

This allows you to create targeting rules based on deployment environment, service identity, or request-scoped baggage without explicitly passing these values.

```python
import logfire
from logfire._internal.config import VariablesOptions
from logfire.variables.config import (
    Rollout,
    RolloutOverride,
    VariableConfig,
    VariablesConfig,
    Variant,
    ValueEquals,
)

variables_config = VariablesConfig(
    variables={
        'agent_prompt': VariableConfig(
            name='agent_prompt',
            variants={
                'standard': Variant(key='standard', serialized_value='"Standard prompt"'),
                'premium': Variant(key='premium', serialized_value='"Premium prompt"'),
            },
            rollout=Rollout(variants={'standard': 1.0}),
            overrides=[
                # This matches baggage set via logfire.set_baggage()
                RolloutOverride(
                    conditions=[ValueEquals(attribute='plan', value='enterprise')],
                    rollout=Rollout(variants={'premium': 1.0}),
                ),
            ],
            json_schema={'type': 'string'},
        ),
    }
)

logfire.configure(variables=VariablesOptions(provider=variables_config))

agent_prompt = logfire.var(name='agent_prompt', default='Default prompt', type=str)


async def main():
    # Baggage is automatically included in variable resolution
    with logfire.set_baggage(plan='enterprise'):
        # No need to pass attributes - baggage is included automatically
        details = await agent_prompt.get()
        print(f'With enterprise baggage: {details.value}')
        #> With enterprise baggage: Premium prompt

    # Without matching baggage, gets the default rollout
    details = await agent_prompt.get()
    print(f'Without baggage: {details.value}')
    #> Without baggage: Standard prompt
```

To disable automatic context enrichment:

```python
import logfire
from logfire._internal.config import VariablesOptions
from logfire.variables.config import VariablesConfig

variables_config = VariablesConfig(variables={})

logfire.configure(
    variables=VariablesOptions(
        provider=variables_config,
        include_resource_attributes_in_context=False,
        include_baggage_in_context=False,
    ),
)
```

## Remote Variable Provider

!!! note "Coming Soon"
    The `LogfireRemoteProvider` allows you to manage variables through the Logfire web interface, with automatic synchronization and real-time updates. Documentation will be added when this feature is available.

    With the remote provider, you'll be able to:

    - Edit prompts and configurations in the Logfire UI
    - See which variants are being served in real-time
    - Track the performance of different variants
    - Roll out changes gradually with confidence

## Complete Example: Support Agent with A/B Testing

Here's a complete example showing a customer support agent with A/B testing on system prompts and configurable model settings:

```python
import logfire
from pydantic import BaseModel
from pydantic_ai import Agent

from logfire._internal.config import VariablesOptions
from logfire.variables.config import (
    Rollout,
    VariableConfig,
    VariablesConfig,
    Variant,
)


class ModelSettings(BaseModel):
    """Configuration for the AI model."""

    model: str
    temperature: float
    max_tokens: int


# Variable configuration with two prompt variants for A/B testing
variables_config = VariablesConfig(
    variables={
        'support_agent_prompt': VariableConfig(
            name='support_agent_prompt',
            variants={
                'v1': Variant(
                    key='v1',
                    serialized_value='"You are a customer support agent. Be helpful and professional."',
                    description='Original prompt',
                    version='1.0.0',
                ),
                'v2': Variant(
                    key='v2',
                    serialized_value='"You are an expert customer support agent. Be empathetic and solution-oriented. Always acknowledge the customer\'s concern before providing assistance."',
                    description='Improved prompt with empathy focus',
                    version='2.0.0',
                ),
            },
            rollout=Rollout(variants={'v1': 0.5, 'v2': 0.5}),  # 50/50 A/B test
            overrides=[],
            json_schema={'type': 'string'},
        ),
        'support_model_settings': VariableConfig(
            name='support_model_settings',
            variants={
                'default': Variant(
                    key='default',
                    serialized_value='{"model": "openai:gpt-4o-mini", "temperature": 0.3, "max_tokens": 500}',
                ),
            },
            rollout=Rollout(variants={'default': 1.0}),
            overrides=[],
            json_schema={'type': 'object'},
        ),
    }
)

# Configure Logfire
logfire.configure(variables=VariablesOptions(provider=variables_config))
logfire.instrument_pydantic_ai()

# Define variables
system_prompt = logfire.var(
    name='support_agent_prompt',
    default='You are a helpful assistant.',
    type=str,
)

model_settings = logfire.var(
    name='support_model_settings',
    default=ModelSettings(model='openai:gpt-4o-mini', temperature=0.3, max_tokens=500),
    type=ModelSettings,
)


async def handle_support_request(user_id: str, message: str) -> str:
    """Handle a customer support request with managed configuration."""
    # Get configuration - same user always gets same variant (deterministic)
    # Using context managers ensures variant info is recorded in baggage
    with await system_prompt.get(targeting_key=user_id) as prompt_details:
        with await model_settings.get(targeting_key=user_id) as settings_details:
            with logfire.span(
                'support_request',
                user_id=user_id,
                prompt_variant=prompt_details.variant,
                model=settings_details.value.model,
            ):
                # Create and run the agent with resolved configuration
                agent = Agent(settings_details.value.model, system_prompt=prompt_details.value)
                result = await agent.run(message)
                return result.output


async def main():
    # Handle requests from different users
    # Each user consistently gets the same variant due to targeting_key
    users = ['user_alice', 'user_bob', 'user_charlie', 'user_diana']

    for user_id in users:
        # Check which variant this user gets
        details = await system_prompt.get(targeting_key=user_id)
        print(f'{user_id} -> prompt variant: {details.variant}')

        # In a real app, you'd handle actual messages:
        # response = await handle_support_request(user_id, "I need help with my order")
```

## Testing with Managed Variables

Use contextual overrides to test specific variable values without modifying configuration:

```python
import logfire
from pydantic import BaseModel

from logfire._internal.config import VariablesOptions
from logfire.variables.config import (
    Rollout,
    VariableConfig,
    VariablesConfig,
    Variant,
)


class ModelSettings(BaseModel):
    model: str
    temperature: float


variables_config = VariablesConfig(
    variables={
        'test_prompt': VariableConfig(
            name='test_prompt',
            variants={
                'production': Variant(
                    key='production', serialized_value='"Production prompt"'
                ),
            },
            rollout=Rollout(variants={'production': 1.0}),
            overrides=[],
            json_schema={'type': 'string'},
        ),
    }
)

logfire.configure(variables=VariablesOptions(provider=variables_config))

system_prompt = logfire.var(name='test_prompt', default='Default prompt', type=str)

model_settings = logfire.var(
    name='model_settings',
    default=ModelSettings(model='gpt-4o-mini', temperature=0.7),
    type=ModelSettings,
)


async def test_prompt_override():
    """Test that prompt overrides work correctly."""
    # Production value from config
    details = await system_prompt.get()
    assert details.value == 'Production prompt'

    # Override for testing
    with system_prompt.override('Test prompt for unit tests'):
        details = await system_prompt.get()
        assert details.value == 'Test prompt for unit tests'

    # Back to production after context exits
    details = await system_prompt.get()
    assert details.value == 'Production prompt'

    print('All prompt override tests passed!')


async def test_model_settings_override():
    """Test overriding structured configuration."""
    # Default value (no config for this variable)
    details = await model_settings.get()
    assert details.value.model == 'gpt-4o-mini'
    assert details.value.temperature == 0.7

    # Override with custom settings
    test_settings = ModelSettings(model='gpt-4', temperature=0.0)
    with model_settings.override(test_settings):
        details = await model_settings.get()
        assert details.value.model == 'gpt-4'
        assert details.value.temperature == 0.0

    print('All model settings override tests passed!')


async def main():
    await test_prompt_override()
    await test_model_settings_override()
```
