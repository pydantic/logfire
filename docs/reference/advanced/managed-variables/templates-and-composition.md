# Template Variables and Composition

Managed variables can contain **Handlebars templates** (`{{placeholder}}`) and **composition references** (`@{other_variable}@`), enabling dynamic values that are assembled from multiple sources and rendered with runtime inputs.

This is especially useful for AI applications where prompts are built from reusable fragments and personalized with request-specific data.

!!! note "Install the variables extra"
    Template rendering requires the `pydantic-handlebars` package, which is installed by the `logfire[variables]` extra:

    ```bash
    pip install 'logfire[variables]'
    ```

    Without this extra, `logfire.template_var()` raises an error immediately so your application does not silently use an unrendered template.

## Template Variables

A **template variable** is a variable whose value contains `{{placeholder}}` expressions that are rendered with typed inputs at resolution time. Define one with `logfire.template_var()` and call `.get(inputs)` to resolve and render in one step:

```python
from pydantic import BaseModel

import logfire

logfire.configure()


class PromptInputs(BaseModel):
    user_name: str
    is_premium: bool = False


prompt = logfire.template_var(
    'system_prompt',
    type=str,
    default='Hello {{user_name}}!{{#if is_premium}} Thank you for being a premium member.{{/if}}',
    inputs_type=PromptInputs,
)

with prompt.get(PromptInputs(user_name='Alice', is_premium=True)) as resolved:
    print(resolved.value)
    #> Hello Alice! Thank you for being a premium member.

with prompt.get(PromptInputs(user_name='Bob')) as resolved:
    print(resolved.value)
    #> Hello Bob!
```

The full resolution pipeline is:

1. **Resolve** — fetch the serialized value from the provider (or use the code default)
2. **Compose** — expand any `@{variable_name}@` references (see [Composition](#variable-composition) below)
3. **Render** — render `{{placeholder}}` Handlebars templates using the provided inputs
4. **Deserialize** — validate and deserialize to the variable's type

`logfire.template_var()` accepts the same parameters as `logfire.var()` plus an `inputs_type` parameter — a Pydantic `BaseModel` (or any type supported by `TypeAdapter`) describing the expected template inputs. It is used for type-safe `.get(inputs)` calls and generates a `template_inputs_schema` for validation.

### Handlebars Syntax

Template variables use [Handlebars](https://handlebarsjs.com/) syntax, powered by the [`pydantic-handlebars`](https://github.com/pydantic/pydantic-handlebars) library. The most common patterns:

| Syntax | Description |
|--------|-------------|
| `{{field}}` | Insert a value |
| `{{obj.nested}}` | Dot-notation access |
| `{{#if field}}...{{/if}}` | Conditional block |
| `{{#unless field}}...{{/unless}}` | Inverse conditional |
| `{{#each items}}...{{/each}}` | Iterate over a list |
| `{{#with obj}}...{{/with}}` | Change context |
| `{{! comment }}` | Comment (not rendered) |

### Structured Template Variables

Template variables work with structured types too. Only string fields containing `{{placeholders}}` are rendered — other fields pass through unchanged:

```python
from pydantic import BaseModel

import logfire

logfire.configure()


class UserContext(BaseModel):
    user_name: str
    tier: str


class AgentConfig(BaseModel):
    instructions: str
    model: str
    temperature: float


agent_config = logfire.template_var(
    'agent_config',
    type=AgentConfig,
    default=AgentConfig(
        instructions='You are helping {{user_name}}, a {{tier}} customer.',
        model='openai:gpt-4o-mini',
        temperature=0.7,
    ),
    inputs_type=UserContext,
)

with agent_config.get(UserContext(user_name='Alice', tier='premium')) as resolved:
    print(resolved.value.instructions)
    #> You are helping Alice, a premium customer.
    print(resolved.value.model)
    #> openai:gpt-4o-mini
```

### Template Validation

When a template variable is pushed to Logfire (via `logfire.variables_push()`), the `template_inputs_schema` is synced alongside the variable's JSON schema. The system validates that all `{{field}}` references in variable values (including values reachable through composition) are compatible with the declared schema.

For example, if your `inputs_type` declares `user_name: str` and `is_premium: bool`, but a version value references `{{unknown_field}}`, the validation will flag this as an error.

## Variable Composition {#variable-composition}

**Composition** lets a variable's value reference other variables using `@{variable_name}@` syntax. When the variable is resolved, `@{ref}@` references are expanded by looking up the referenced variable and substituting its value.

This is useful for building values from reusable fragments:

```python
import logfire

logfire.configure()

# A reusable instruction fragment
safety_rules = logfire.var(
    'safety_rules',
    type=str,
    default='Never share personal data. Always be respectful.',
)

# A prompt that includes the safety rules via composition
agent_prompt = logfire.var(
    'agent_prompt',
    type=str,
    default='You are a helpful assistant. @{safety_rules}@',
)

with agent_prompt.get() as resolved:
    print(resolved.value)
    #> You are a helpful assistant. Never share personal data. Always be respectful.
```

When `safety_rules` is updated in the Logfire UI, all variables that reference `@{safety_rules}@` automatically pick up the new value — no code changes or redeployment required.

### Composition Control Flow

The `@{}@` syntax runs through the full Handlebars engine (just with `@{` / `}@` as the delimiter pair instead of the default `{{` / `}}`), so any expression form that works in Handlebars also works here — simple references, dotted field reads, block helpers, and helper sub-expressions:

| Syntax | Description |
|--------|-------------|
| `@{variable_name}@` | Insert a variable's value |
| `@{variable.field}@` | Access a nested field |
| `@{#if variable}@...@{else}@...@{/if}@` | Conditional on whether a variable is set |
| `@{#if user.active}@...@{/if}@` | Conditional on a dotted field |
| `@{#each items}@...@{/each}@` | Iterate over a list variable |
| `@{#each items}@@{../top}@@{/each}@` | Access an outer-scope value from inside a block |

### Composition Tracking

Every `@{ref}@` expansion is recorded in the resolution result. You can inspect which variables were composed and their values:

```python skip="true"
with agent_prompt.get() as resolved:
    for ref in resolved.composed_from:
        print(f"  {ref.name}: version={ref.version}, label={ref.label}")
```

These composition details are also recorded as span attributes, so you can see the full composition chain in your Logfire traces.

### Combining Templates and Composition

Template variables and composition work together. A common pattern is to compose reusable fragments via `@{ref}@` and render runtime inputs via `{{}}`:

```python skip="true"
from pydantic import BaseModel

import logfire

logfire.configure()


class ChatInputs(BaseModel):
    user_name: str
    language: str


# Reusable fragment (no template inputs)
tone_instructions = logfire.var(
    'tone_instructions',
    type=str,
    default='Be friendly and concise.',
)

# Template variable that composes the fragment and renders inputs
chat_prompt = logfire.template_var(
    'chat_prompt',
    type=str,
    default='You are helping {{user_name}}. Respond in {{language}}. @{tone_instructions}@',
    inputs_type=ChatInputs,
)

# Resolution: compose @{tone_instructions}@ first, then render {{user_name}} and {{language}}
with chat_prompt.get(ChatInputs(user_name='Alice', language='French')) as resolved:
    print(resolved.value)
    # "You are helping Alice. Respond in French. Be friendly and concise."
```

### Cycle Detection

The system detects circular references during validation. If variable A references `@{B}@` and variable B references `@{A}@`, `logfire.variables_validate()` reports the cycle, and `logfire.variables_push(strict=True)` fails instead of applying the invalid configuration. This prevents infinite loops during resolution.
