# Managed Variables

Managed variables let you define and reference configuration in your code, but control the runtime values from the Logfire UI without redeploying.

Define a variable once with a sensible default, deploy your application, then iterate on the values in production. You can target specific populations (opted-in beta users, internal developers, enterprise customers, etc.) using flexible targeting rules that integrate with your existing OpenTelemetry attributes.

Changes take effect quickly, and every variable resolution is visible in your traces. This trace-level visibility means you can correlate application behavior directly with specific configuration versions, enabling A/B testing, automated prompt optimization, and online evaluations using the same observability data you're already sending to Logfire.

## What Are Managed Variables?

Managed variables are a way to externalize runtime configuration from your code. While they're especially powerful for AI applications (where prompt iteration is frequently critical), they work for any configuration you want to change without redeploying:

- **Any type**: Use primitives (strings, bools, ints) or structured types (dataclasses, Pydantic models, etc.)
- **Observability-integrated**: Every variable resolution creates a span, and using the context manager automatically sets baggage so downstream operations are tagged with which label and version was used
- **Versions and labels**: Create immutable version snapshots of your variable's value, and assign labels (like `production`, `staging`, `canary`) that point to specific versions
- **Rollouts and targeting**: Control what percentage of requests receive each labeled version, and route specific users or segments based on attributes

### Versions and Labels

Managed variables use a **versions + labels** model inspired by how Docker tags and git branches work:

- **Versions** are immutable, sequentially numbered snapshots of a variable's value (v1, v2, v3, ...). Once created, a version's value never changes.
- **Labels** are mutable pointers that reference a specific version. You can move a label to point to a different version at any time — instantly changing what value is served to traffic assigned to that label.

For example, you might have a prompt variable with three versions:

| Version | Value |
|---------|-------|
| v1 | "You are a helpful assistant." |
| v2 | "You are a helpful assistant. Be concise." |
| v3 | "You are an expert assistant. Provide thorough, well-structured responses." |

And two labels pointing to those versions:

| Label | Points to | Effect |
|-------|-----------|--------|
| `production` | v2 | Most users get the concise prompt |
| `canary` | v3 | 10% of traffic tests the detailed prompt |

To roll out v3 to everyone, just move the `production` label from v2 to v3. To roll back, move it back to v2. No new versions need to be created — the label is just a pointer.

!!! tip "Code default fallback"
    If no labels are configured in the rollout, or if rollout weights sum to less than 1.0, the remaining traffic uses the **code default** (the `default` value passed to `logfire.var()`). To direct remaining traffic to the latest version instead, create a label that references `latest` and include it in your rollout.

!!! note "Code default as safety net"
    The `default` value you pass to `logfire.var()` serves as an always-available fallback hard-coded into your source code. If no versions have been created yet, or if the remote configuration is unreachable due to a networking issue, or if a remote value fails validation against your type, the SDK returns the code default instead of raising an error. This means your application always has a working value — the remote configuration improves it, but never breaks it.

## Structured Configuration

While you can use simple primitive types as variables, you can also use them with **structured types** that group related configuration together:

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
    name='agent_config',
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

- **Coherent versions**: A version isn't just "instructions v2", it's a complete configuration where all the pieces work well together. The temperature that works with a detailed prompt might not work as well with a concise one.
- **Atomic changes**: When you create a new version, all settings change together. No risk of mismatched configurations.
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

- **Iteration speed**: Create a new version in the Logfire UI and see the effect in real traces immediately
- **A/B testing**: Assign labels to different versions and split traffic between them to compare performance
- **Gradual rollouts**: Point a `canary` label at a new version with 5% of traffic, watch the metrics, then move `production` to the same version
- **Instant rollback**: If a version is causing problems, move the label back to the previous version in seconds, with no deploy required
- **Full history**: Every version is immutable and preserved, so you can always see exactly what was served and when

## How It Works

Here's the typical workflow using the `AgentConfig` example from above:

1. **Define the variable in code** with your current configuration as the default
2. **Deploy your application**: it starts using the default immediately
3. **Push the variable to Logfire** using `logfire.variables_push()` to sync metadata and schemas
4. **Create versions** in the Logfire UI: add your initial value as version 1, then create additional versions with different configurations
5. **Assign labels**: create labels like `production` and `canary`, pointing them at specific versions
6. **Set up a rollout**: configure 90% of traffic to the `production` label and 10% to `canary`
7. **Monitor in real-time**: filter traces by label to compare response quality, latency, and token usage
8. **Adjust based on data**: if the canary version performs better, move the `production` label to that version

## API Keys {#api-keys}

Managed variables require API keys with the appropriate scopes. There are two scenarios that each require a key with a different scope:

- **Reading variables at runtime** (in your application): an API key with the `project:read_variables` scope (or `project:read_external_variables` if you only need access to external variables, e.g. in client-side apps), set via the `LOGFIRE_API_KEY` environment variable.
- **Pushing variable definitions** (syncing schemas from code): an API key with the `project:write_variables` scope, used with `logfire.variables_push()` and other related write APIs. This is separate from the write token (`LOGFIRE_TOKEN`) used to send traces.

| Scope | Purpose |
|-------|---------|
| `project:read_variables` | Read all variables via SDK or OFREP |
| `project:write_variables` | Create, update, and delete variables and variable types |
| `project:read_external_variables` | Read only external variables via OFREP (for client-side apps) |

You can create and manage API keys in your project's **Settings > API Keys** page. For more details on external variables and client-side access patterns, see [External Variables and OFREP](external.md#api-key-scopes-for-variables).

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
    name='support_agent_config',
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
- Sets baggage with the variable name, selected label, and version

When using the Logfire SDK, baggage values are automatically added as attributes to all downstream spans. This means any spans created inside the context manager will be tagged with which label and version was used, making it easy to filter and compare behavior in the Logfire UI.

```python skip="true"
from pydantic_ai import Agent


async def handle_support_ticket(user_id: str, message: str) -> str:
    """Handle a customer support request."""
    # Get the configuration - same user always gets the same label
    with agent_config.get(targeting_key=user_id) as config:
        # Inside this context, baggage is set with the label and version info

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

The `targeting_key` ensures deterministic label selection: the same user always gets the same label, which is essential for application behavior consistency when A/B testing.

In practice, depending on your application structure, you may want to use `tenant_id` or another identifier for `targeting_key` instead of `user_id`. If no `targeting_key` is provided and there's an active trace, the `trace_id` is used automatically to ensure consistent behavior within a single request.

**Requesting a specific label:**

You can explicitly request a specific label when calling `.get()`:

```python skip="true"
# Always get the production version for this call
with agent_config.get(targeting_key=user_id, label='production') as config:
    ...

# Get the staging version for testing
with agent_config.get(label='staging') as config:
    ...
```

This bypasses the rollout weights and directly resolves the value from the specified label.

### Variable Parameters

| Parameter | Description                                                             |
|-----------|-------------------------------------------------------------------------|
| `name` | Unique identifier for the variable                                      |
| `type` | Expected type for validation; can be a primitive type or Pydantic model |
| `default` | Default value when no configuration is found (can also be a function)   |
