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

# Use the variable in your application
async def get_agent_response(user_message: str) -> str:
    instructions = await agent_instructions.get()
    # Use instructions with your AI framework...
    return f"Instructions: {instructions}"
```

### Variable Parameters

| Parameter | Description |
|-----------|-------------|
| `name` | Unique identifier for the variable |
| `default` | Default value when no configuration is found (can also be a function) |
| `type` | Expected type(s) for validation — can be a single type or sequence of types |

### Getting Variable Values

Variables are resolved asynchronously:

```python
# Get just the value
value = await my_variable.get()

# Get full resolution details (includes variant info, any errors, etc.)
details = await my_variable.get_details()
print(details.value)    # The resolved value
print(details.variant)  # Which variant was selected (if any)
```

### Targeting and Attributes

You can pass targeting information to influence which variant is selected:

```python
# Target a specific user for consistent A/B test assignment
value = await agent_instructions.get(
    targeting_key='user_123',  # Used for deterministic variant selection
    attributes={'plan': 'enterprise', 'region': 'us-east'},
)
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


async def generate_response(creative_mode: bool = False):
    if creative_mode:
        # Override temperature for this context only
        with model_temperature.override(1.0):
            temp = await model_temperature.get()
            print(f"Using creative temperature: {temp}")  # 1.0
            # ... generate response ...
    else:
        temp = await model_temperature.get()
        print(f"Using default temperature: {temp}")  # 0.7
        # ... generate response ...
```

### Dynamic Override Functions

You can also override with a function that computes the value dynamically:

```python
def get_temperature_for_context(targeting_key: str | None, attributes: dict | None) -> float:
    """Compute temperature based on context."""
    if attributes and attributes.get('mode') == 'creative':
        return 1.0
    return 0.5


async def process_request():
    with model_temperature.override(get_temperature_for_context):
        # Temperature will be computed based on the attributes passed to get()
        temp = await model_temperature.get(attributes={'mode': 'creative'})
        print(temp)  # 1.0
```

## Local Variable Provider

The `LogfireLocalProvider` lets you configure variables from a local configuration object. This is useful for development, testing, or self-hosted deployments where you want full control over variable values.

### Configuration Structure

Variables are configured using `VariablesConfig`, which defines:

- **Variables**: Each variable has variants (possible values) and rollout rules
- **Variants**: Named values that can be selected
- **Rollouts**: Probability weights for selecting variants
- **Overrides**: Conditional rules that change the rollout based on attributes

### Example: Configuring an AI Agent

```python
import logfire
from logfire._internal.config import VariablesOptions
from logfire.variables.config import (
    VariablesConfig,
    VariableConfig,
    Variant,
    Rollout,
    RolloutOverride,
    ValueEquals,
)

# Define your variable configurations
config = VariablesConfig(
    variables={
        'agent_system_prompt': VariableConfig(
            name='agent_system_prompt',
            variants={
                'default': Variant(
                    key='default',
                    serialized_value='"You are a helpful AI assistant."',
                ),
                'detailed': Variant(
                    key='detailed',
                    serialized_value='"You are a helpful AI assistant. Always provide detailed explanations with examples. Structure your responses clearly."',
                ),
                'concise': Variant(
                    key='concise',
                    serialized_value='"You are a helpful AI assistant. Be brief and to the point."',
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
        'model_config': VariableConfig(
            name='model_config',
            variants={
                'standard': Variant(
                    key='standard',
                    serialized_value='{"model": "gpt-4o-mini", "temperature": 0.7, "max_tokens": 1000}',
                ),
                'premium': Variant(
                    key='premium',
                    serialized_value='{"model": "gpt-4o", "temperature": 0.5, "max_tokens": 4000}',
                ),
            },
            rollout=Rollout(variants={'standard': 1.0}),
            overrides=[
                RolloutOverride(
                    conditions=[ValueEquals(attribute='plan', value='enterprise')],
                    rollout=Rollout(variants={'premium': 1.0}),
                ),
            ],
            json_schema={'type': 'object'},
        ),
    }
)

# Configure Logfire with the local provider
logfire.configure(
    variables=VariablesOptions(provider=config),
)
```

### Using Configured Variables

```python
from pydantic import BaseModel


class ModelConfig(BaseModel):
    model: str
    temperature: float
    max_tokens: int


# Define variables with proper types
system_prompt = logfire.var(
    name='agent_system_prompt',
    default='You are a helpful assistant.',
    type=str,
)

model_config = logfire.var(
    name='model_config',
    default=ModelConfig(model='gpt-4o-mini', temperature=0.7, max_tokens=1000),
    type=ModelConfig,
)


async def run_agent(user_id: str, user_plan: str):
    # Get the prompt - variant selection is deterministic per user
    prompt = await system_prompt.get(
        targeting_key=user_id,
        attributes={'plan': user_plan},
    )

    # Get model configuration
    config = await model_config.get(
        targeting_key=user_id,
        attributes={'plan': user_plan},
    )

    print(f"Using prompt: {prompt}")
    print(f"Using model: {config.model} with temperature {config.temperature}")

    # Use with your AI framework...
```

### Variant Selection

Variants are selected based on:

1. **Overrides**: Conditions are evaluated in order; the first matching override's rollout is used
2. **Rollout weights**: Variants are selected probabilistically based on their weights
3. **Targeting key**: When provided, ensures consistent selection for the same key (useful for A/B tests)

If rollout weights sum to less than 1.0, there's a chance no variant is selected and the code default is used.

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
    RolloutOverride,
    Rollout,
    ValueEquals,
    ValueIsIn,
    KeyIsPresent,
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
# These are automatically included in variable resolution
with logfire.set_baggage(user_id='user_123', plan='enterprise'):
    # No need to pass attributes - baggage is included automatically
    prompt = await system_prompt.get()
```

To disable this behavior:

```python
logfire.configure(
    variables=VariablesOptions(
        provider=config,
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

## Complete Example: AI Agent with Managed Prompts

Here's a complete example showing how to use managed variables with an AI agent:

```python
import logfire
from pydantic import BaseModel
from logfire._internal.config import VariablesOptions
from logfire.variables.config import (
    VariablesConfig,
    VariableConfig,
    Variant,
    Rollout,
    RolloutOverride,
    ValueEquals,
)


# Configuration types
class AgentConfig(BaseModel):
    model: str
    temperature: float
    max_tokens: int


# Variable configuration
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
                    serialized_value='"You are an expert customer support agent. Be empathetic, helpful, and solution-oriented. Always acknowledge the customer\'s concern before providing assistance."',
                    description='Improved prompt with empathy focus',
                    version='2.0.0',
                ),
            },
            rollout=Rollout(variants={'v1': 0.5, 'v2': 0.5}),  # 50/50 A/B test
            overrides=[],
            json_schema={'type': 'string'},
        ),
        'support_agent_config': VariableConfig(
            name='support_agent_config',
            variants={
                'default': Variant(
                    key='default',
                    serialized_value='{"model": "gpt-4o-mini", "temperature": 0.3, "max_tokens": 500}',
                ),
            },
            rollout=Rollout(variants={'default': 1.0}),
            overrides=[],
            json_schema={'type': 'object'},
        ),
    }
)

# Configure Logfire
logfire.configure(
    variables=VariablesOptions(provider=variables_config),
)

# Define variables
system_prompt = logfire.var(
    name='support_agent_prompt',
    default='You are a helpful assistant.',
    type=str,
)

agent_config = logfire.var(
    name='support_agent_config',
    default=AgentConfig(model='gpt-4o-mini', temperature=0.3, max_tokens=500),
    type=AgentConfig,
)


async def handle_support_request(user_id: str, message: str) -> str:
    """Handle a customer support request."""

    # Get configuration - same user always gets same variant
    prompt = await system_prompt.get(targeting_key=user_id)
    config = await agent_config.get(targeting_key=user_id)

    # Get details to log which variant is being used
    prompt_details = await system_prompt.get_details(targeting_key=user_id)

    with logfire.span(
        'support_agent_response',
        user_id=user_id,
        prompt_variant=prompt_details.variant,
        model=config.model,
    ):
        # Here you would call your AI framework
        # For example with PydanticAI:
        #
        # from pydantic_ai import Agent
        # agent = Agent(config.model, system_prompt=prompt)
        # result = await agent.run(message)
        # return result.data

        return f"[Using {prompt_details.variant}] Response to: {message}"


# Example usage
async def main():
    # Simulate requests from different users
    for user_id in ['user_1', 'user_2', 'user_3', 'user_4']:
        response = await handle_support_request(user_id, "I need help with my order")
        print(f"{user_id}: {response}")


if __name__ == '__main__':
    import asyncio
    asyncio.run(main())
```

## Testing with Managed Variables

Use contextual overrides to test specific variable values:

```python
import pytest


async def test_support_agent_with_v2_prompt():
    """Test the support agent with the v2 prompt variant."""

    v2_prompt = "You are an expert customer support agent..."

    with system_prompt.override(v2_prompt):
        response = await handle_support_request('test_user', 'Help!')
        # Assert expected behavior with v2 prompt
        assert 'test_user' in response or response  # Example assertion


async def test_support_agent_with_custom_config():
    """Test with a completely custom configuration."""

    custom_config = AgentConfig(model='gpt-4', temperature=0.0, max_tokens=100)

    with agent_config.override(custom_config):
        config = await agent_config.get()
        assert config.model == 'gpt-4'
        assert config.temperature == 0.0
```
