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

### Recursive Resolution

!!! warning "Different from plain Handlebars"
    Standard Handlebars expressions like `{{greeting}}` perform a **one-shot string substitution**: whatever string `greeting` resolves to appears verbatim in the output. If that string happens to contain `{{name}}`, the inner `{{name}}` is *not* re-evaluated — it ends up in the output as the literal text `{{name}}`.

    `@{...}@` composition does the opposite: when the SDK substitutes a referenced variable, it first **fully resolves** that variable — including expanding any `@{...}@` references *inside* it — before splicing the result in. This is the main semantic difference between composition and plain Handlebars, and it trips up people coming from "normal" Handlebars where the assumption is that values are inert strings.

Concretely, composition walks the reference graph at resolution time. A tree like `parent → @{middle}@ → @{leaf}@` resolves leaf-first, builds `middle`, then substitutes the result into `parent`:

```python skip="true"
import logfire

logfire.configure()

leaf = logfire.var('leaf', type=str, default='LEAF')
middle = logfire.var('middle', type=str, default='middle wraps @{leaf}@')
parent = logfire.var('parent', type=str, default='top: @{middle}@')

with parent.get() as resolved:
    print(resolved.value)
    #> top: middle wraps LEAF
    # composed_from mirrors the tree:
    #   middle (composed_from: [leaf])
```

Contrast with plain Handlebars rendering, where `{{...}}` only substitutes — no graph walk, no re-rendering of values that happen to look template-like:

```python skip="true"
from pydantic_handlebars import render

render('{{greeting}}', {'greeting': 'Hello, {{name}}!', 'name': 'Alice'})
#> 'Hello, {{name}}!'   ← the inner {{name}} is NOT re-rendered
```

### Cycle and depth guards

Because resolution walks an arbitrary graph, two failure modes need explicit handling: cycles (`A → @{B}@`, `B → @{A}@`) and deep chains. Both are caught at two layers:

- **Push / sync time** — `logfire.variables_validate()` reports reference errors and cycles; `logfire.variables_push(strict=True)` fails instead of applying an invalid configuration. The walk covers the *full* reachable graph (local code defaults and server-stored label values), so a cycle whose midpoint is a server-only variable is still detected. This is the loud-by-default path.
- **Runtime** — if an invalid composition slips through (e.g. a server value changed between validation and the next resolve), `Variable.get()` catches the cycle (via a visited-set) or depth overflow (`MAX_COMPOSITION_DEPTH = 20`) and falls back to the variable's *code default* with a `RuntimeWarning`. The exception is recorded on `ResolvedVariable.exception` and the resolution reason becomes `'other_error'` so callers can detect and react. The same fallback applies when a `@{ref}@` points at a variable that doesn't exist at runtime — this differs from a missing `{{field}}` (Handlebars' empty-string substitution); composition treats unresolvable references as a real failure.

```python skip="true"
import warnings

# Suppose the server config has parent.latest = "@{missing_at_runtime}@"
with warnings.catch_warnings(record=True) as caught:
    warnings.simplefilter('always')
    with parent.get() as resolved:
        assert resolved.value == 'code default for parent'
        assert resolved.reason == 'other_error'
        assert isinstance(resolved.exception, logfire.variables.VariableCompositionError)
    assert any('composition failed' in str(w.message) for w in caught)
```
