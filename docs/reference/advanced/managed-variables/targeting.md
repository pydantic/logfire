# Targeting Users and Segments

## Targeting Key

The `targeting_key` parameter ensures deterministic label selection. The same key always produces the same label, which is useful for:

- **Consistent user experience**: You typically want users to see consistent configuration behavior within a session, or even across sessions. You may also want all users within a single tenant to receive the same label.
- **Debugging**: By controlling the `targeting_key`, you can deterministically get the same configuration that a user received. Note that this reproduces the *configuration*, not the exact behavior; if your application includes stochastic elements like LLM calls, outputs will still vary.

```python skip="true"
# User-based targeting
with agent_config.get(targeting_key=user_id) as config:
    ...

# Request-based targeting (if no targeting_key provided and there's an active trace,
# the trace ID is used automatically)
with agent_config.get() as config:
    ...
```

## Setting Targeting Key via Context

Instead of passing `targeting_key` to every `.get()` call, you can set it once at a higher level using `targeting_context`. This is useful when you want to set the targeting key early in your request lifecycle (e.g., in middleware) and have it apply to all variable resolutions within that context:

```python skip="true"
from logfire.variables import targeting_context

async def handle_request(user_id: str, message: str) -> str:
    # Set targeting key once for all variables in this context
    with targeting_context(user_id):
        # All variable resolutions here use user_id as the targeting key
        with agent_config.get() as config:
            ...
        with another_variable.get() as other:
            ...
```

**Variable-specific targeting:**

Different variables may need different targeting strategies. For example, you might want to target by `user_id` for personalization features but by `organization_id` for billing-related features. You can specify which variables a targeting context applies to:

```python skip="true"
from logfire.variables import targeting_context

# Define variables
personalization_config = logfire.var(name='personalization', type=PersonalizationConfig, default=...)
billing_config = logfire.var(name='billing', type=BillingConfig, default=...)

async def handle_request(user_id: str, org_id: str) -> None:
    # Set different targeting keys for different variables
    with targeting_context(org_id, variables=[billing_config]):
        with targeting_context(user_id, variables=[personalization_config]):
            # billing_config uses org_id as targeting key
            # personalization_config uses user_id as targeting key
            with billing_config.get() as billing:
                ...
            with personalization_config.get() as personalization:
                ...
```

**Combining default and variable-specific targeting:**

You can set a default targeting key for all variables while overriding it for specific ones. Variable-specific targeting always takes precedence over the default, regardless of nesting order:

```python skip="true"
from logfire.variables import targeting_context

# Set default targeting for all variables, but use org_id for billing
with targeting_context(user_id):  # default for all variables
    with targeting_context(org_id, variables=[billing_config]):  # specific override
        # billing_config uses org_id
        # all other variables use user_id
        ...

# Order doesn't matter - specific always wins
with targeting_context(org_id, variables=[billing_config]):
    with targeting_context(user_id):
        # Same result: billing_config uses org_id, others use user_id
        ...
```

**Priority order:**

When resolving the targeting key for a variable, the following priority order is used:

1. **Call-site explicit**: `variable.get(targeting_key='explicit')` - always wins
2. **Variable-specific context**: Set via `targeting_context(key, variables=[var])`
3. **Default context**: Set via `targeting_context(key)` without specifying variables
4. **Trace ID fallback**: If there's an active trace and no targeting key is set, the trace ID is used

## Attributes for Conditional Rules

Pass attributes to enable condition-based targeting:

```python skip="true"
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

These attributes can be used in conditional rules to route specific segments to specific labels:

```python skip="true"
from logfire.variables.config import (
    LabeledValue,
    LabelRef,
    LatestVersion,
    Rollout,
    RolloutOverride,
    ValueEquals,
    VariableConfig,
    VariablesConfig,
)

variables_config = VariablesConfig(
    variables={
        'support_agent_config': VariableConfig(
            name='support_agent_config',
            latest_version=LatestVersion(
                version=2,
                serialized_value='{"instructions": "Provide detailed, thorough responses...", ...}',
            ),
            labels={
                'standard': LabeledValue(
                    version=1,
                    serialized_value='{"instructions": "Be helpful and concise.", ...}',
                ),
                'premium': LabelRef(
                    version=2,
                    ref='latest',
                ),
            },
            # Default: everyone gets 'standard'
            rollout=Rollout(labels={'standard': 1.0}),
            overrides=[
                # Enterprise plan users always get the premium label
                RolloutOverride(
                    conditions=[ValueEquals(attribute='plan', value='enterprise')],
                    rollout=Rollout(labels={'premium': 1.0}),
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
    # config.label will be 'premium' because of the override
    ...

with agent_config.get(
    targeting_key=user_id,
    attributes={'plan': 'free'},  # Does not match override
) as config:
    # config.label will be 'standard' (the default routing)
    ...
```

## Automatic Context Enrichment

By default, Logfire automatically includes additional context when resolving variables:

- **Resource attributes**: OpenTelemetry resource attributes (service name, version, environment)
- **Baggage**: Values set via `logfire.set_baggage()`

This means your targeting rules can match against service identity or request-scoped baggage without explicitly passing them.

**Example: Plan-based targeting with baggage**

If your application sets the user's plan as baggage early in the request lifecycle, you can use it for targeting without passing it explicitly to every variable resolution:

```python skip="true"
# In your middleware or request handler, set the plan once
with logfire.set_baggage(plan='enterprise'):
    # ... later in your application code ...
    with agent_config.get(targeting_key=user_id) as config:
        # The variable resolution automatically sees plan='enterprise'
        # If you have an override targeting enterprise users, it will match
        ...
```

This is useful when you want different configurations based on user plan. For example, enterprise users might get a prompt version that references tools only available to them.

**Example: Environment-based targeting with resource attributes**

Resource attributes like `deployment.environment` are automatically included, allowing you to use different configurations in different environments without code changes:

- Use a more experimental prompt on staging to test changes before production
- Enable verbose logging in development but not in production
- Route all staging traffic to a `staging` label that points at the latest version

To disable automatic context enrichment:

```python skip="true"
logfire.configure(
    variables=logfire.VariablesOptions(
        include_resource_attributes_in_context=False,
        include_baggage_in_context=False,
    ),
)
```
