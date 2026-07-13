# Template Variables and Composition

Managed variables can contain **Handlebars templates** (`{{placeholder}}`) and **composition references** (`@{other_variable}@`), enabling dynamic values that are assembled from multiple sources and rendered with runtime inputs.

This is especially useful for AI applications where prompts are built from reusable fragments and personalized with request-specific data.

!!! note "Install the variables extra"
    Managed variables require the `logfire[variables]` extra (which installs `pydantic` and `pydantic-handlebars`):

    ```bash
    pip install 'logfire[variables]'
    ```

    `logfire.var()` and `logfire.template_var()` raise an `ImportError` immediately if the extra is missing, so a missing dependency is a clear error rather than, e.g., a composition value silently falling back to its code default. Plain `import logfire` and the rest of the SDK keep working without it.

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

1. **Resolve**: fetch the serialized value from the provider (or use the code default)
2. **Compose**: expand any `@{variable_name}@` references (see [Composition](#variable-composition) below)
3. **Render**: render `{{placeholder}}` Handlebars templates using the provided inputs
4. **Deserialize**: validate and deserialize to the variable's type

`logfire.template_var()` accepts the same parameters as `logfire.var()` plus an `inputs_type` parameter, a Pydantic `BaseModel` (or any type supported by `TypeAdapter`) describing the expected template inputs. It is used for type-safe `.get(inputs)` calls and generates a `template_inputs_schema` for validation.

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

Template variables work with structured types too. Only string fields containing `{{placeholders}}` are rendered. Other fields pass through unchanged:

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

#### Render-time mismatch policy

Push-time validation is a pre-flight check. At **render time**, `TemplateVariable.get(inputs)` can also react when the resolved (post-composition) template references a `{{field}}` not declared in `inputs_type`. An undeclared field otherwise renders to the empty string (matching Handlebars). The behaviour is controlled by `template_mismatch_policy`:

- `'warn'` (default): emit a `RuntimeWarning` and render anyway (undeclared fields become empty strings).
- `'error'`: raise `TemplateInputsMismatchError` instead of rendering.
- `'ignore'`: render silently, no warning.

Set it per-variable on [`template_var()`][logfire.Logfire.template_var], or per-Logfire-instance on `VariablesOptions` / `LocalVariablesOptions`. The variable-level value wins when set (even when it *relaxes* the instance setting); otherwise the instance setting applies, falling back to `'warn'`.

```py skip-run="true" skip-reason="requires-pydantic-handlebars"
from pydantic import BaseModel

import logfire

logfire.configure()


class PromptInputs(BaseModel):
    user_name: str


# Fail loudly instead of silently rendering an undeclared `{{field}}` as empty.
prompt = logfire.template_var(
    'system_prompt',
    default='Hello {{user_name}}',
    inputs_type=PromptInputs,
    template_mismatch_policy='error',
)
```

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

When `safety_rules` is updated in the Logfire UI, all variables that reference `@{safety_rules}@` automatically pick up the new value: no code changes or redeployment required.

### Composition Control Flow

The `@{}@` syntax runs through the full Handlebars engine (just with `@{` / `}@` as the delimiter pair instead of the default `{{` / `}}`), so any expression form that works in Handlebars also works here: simple references, dotted field reads, block helpers, and helper sub-expressions:

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

```python
import logfire

logfire.configure()

logfire.var('city', type=str, default='Paris')
report = logfire.var('report', type=str, default='Weather in @{city}@: sunny.')

with report.get() as resolved:
    for ref in resolved.composed_from:
        print(f'{ref.name}={ref.value!r} reason={ref.reason}')
        #> city='Paris' reason=code_default
```

These composition details are also recorded as span attributes, so you can see the full composition chain in your Logfire traces.

### Combining Templates and Composition

Template variables and composition work together. A common pattern is to compose reusable fragments via `@{ref}@` and render runtime inputs via `{{}}`:

```python
from pydantic import BaseModel

import logfire

logfire.configure()


class ChatInputs(BaseModel):
    user_name: str
    language: str


# Reusable fragment (no template inputs)
logfire.var('tone_instructions', type=str, default='Be friendly and concise.')

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
    #> You are helping Alice. Respond in French. Be friendly and concise.
```

!!! warning "Don't compose a template variable into a plain variable"
    Composition flows one way: a `template_var()` may compose plain `var()` fragments (as above), but a plain `var()` should **not** compose a `template_var()`. A plain variable has no `inputs_type`, so a composed template's `{{placeholder}}` expressions can never receive inputs when resolved through it. They'd just render empty. Logfire emits a `RuntimeWarning` at declaration time if you do this. If you need to render the composed template's inputs, make the composing variable a `template_var()` too, with an `inputs_type` that covers the placeholders.

### Recursive Resolution

!!! warning "Different from plain Handlebars"
    Standard Handlebars expressions like `{{greeting}}` perform a **one-shot string substitution**: whatever string `greeting` resolves to appears verbatim in the output. If that string happens to contain `{{name}}`, the inner `{{name}}` is *not* re-evaluated. It ends up in the output as the literal text `{{name}}`.

    `@{...}@` composition does the opposite: when the SDK substitutes a referenced variable, it first **fully resolves** that variable (including expanding any `@{...}@` references *inside* it) before splicing the result in.

Concretely, composition walks the reference graph at resolution time. A tree like `parent → @{middle}@ → @{leaf}@` resolves leaf-first, builds `middle`, then substitutes the result into `parent`:

```python
import logfire

logfire.configure()

logfire.var('leaf', type=str, default='LEAF')
logfire.var('middle', type=str, default='middle wraps @{leaf}@')
parent = logfire.var('parent', type=str, default='top: @{middle}@')

with parent.get() as resolved:
    print(resolved.value)
    #> top: middle wraps LEAF
    # composed_from mirrors the tree:
    print(f'{resolved.composed_from[0].name} -> {resolved.composed_from[0].composed_from[0].name}')
    #> middle -> leaf
```

Contrast with plain Handlebars rendering, where `{{...}}` only substitutes: no graph walk, no re-rendering of values that happen to look template-like:

```python
from pydantic_handlebars import render

print(render('{{greeting}}', {'greeting': 'Hello, {{name}}!', 'name': 'Alice'}))
#> Hello, {{name}}!
```

### Failure handling: missing references, cycles, and depth

Composition follows standard Handlebars semantics, with one extra rule for choosing *which* value to render. Where a broken reference lives determines what happens.

**A provider/stored value (and an `override()`) is composed strictly.** If any `@{ref}@` (or a dotted `@{ref.field}@`) in it can't be resolved, the value is discarded and resolution falls back to the variable's **code default**, with a `RuntimeWarning`. Cycles (`A → @{B}@`, `B → @{A}@`) and deep chains (`MAX_COMPOSITION_DEPTH = 20`) fall back the same way. The triggering exception is recorded on `ResolvedVariable.exception` and `reason` becomes `'other_error'`, so callers can detect and react.

This is the useful part: rather than serve a value that's been assembled *around* a missing fragment, resolution falls back to a value that's known to be complete on its own. A prompt that composes `@{persona}@ @{safety_rules}@` won't be served as just the persona with the safety rules silently dropped. If `@{safety_rules}@` can't be resolved, you get the variable's self-contained code default instead.

```python
import warnings

import logfire

logfire.configure()

logfire.var('persona', type=str, default='You are a helpful assistant.')
system_prompt = logfire.var(
    'system_prompt',
    type=str,
    default='You are a helpful assistant. Always follow the safety policy.',
)

with warnings.catch_warnings(record=True) as caught:
    warnings.simplefilter('always')
    # Simulate a stored value (via override, which is composed strictly too) that builds the
    # prompt from one resolvable fragment and one that's been deleted or mistyped. Instead of
    # serving "You are a helpful assistant. " (silently missing the safety policy), resolution
    # falls back to the complete, self-contained code default.
    with system_prompt.override('@{persona}@ @{safety_rules}@'):
        with system_prompt.get() as resolved:
            print(resolved.value)
            #> You are a helpful assistant. Always follow the safety policy.
    print(any('composition failed' in str(w.message) for w in caught))
    #> True
```

**The code default is the lenient last resort.** When resolution composes the code default (whether it's the active value or the target of a fallback) there is nowhere further to go, so a missing `@{ref}@` in it renders as an **empty string** (and `@{#if missing}@` takes the else branch), like standard Handlebars and like a missing `{{field}}` input. A `RuntimeWarning` still names the issue; only a *structural* failure (a cycle or unparseable template) falls back one more step, to the raw uncomposed default.

The trade-off is worth understanding: because the code default is itself composed (so it too can be built from `@{fragments}@`), a broken reference *in a code default* has nothing to fall back to and will surface an incomplete value at runtime. Keep code defaults self-contained where correctness matters, and lean on push / sync-time validation (below) to catch broken references before they ship.

```python
import warnings

import logfire

logfire.configure()

greeting = logfire.var('greeting_with_missing_ref', type=str, default='Hello @{absent_name}@, welcome!')

with warnings.catch_warnings(record=True) as caught:
    warnings.simplefilter('always')
    with greeting.get() as resolved:
        # `@{absent_name}@` has nowhere to fall back, so it renders empty.
        print(resolved.value)
        #> Hello , welcome!
        print(resolved.reason)
        #> code_default
    print(any('code default has unresolved composition reference' in str(w.message) for w in caught))
    #> True
```

**Push / sync time is the real safety net.** `logfire.variables_validate()` reports missing references and cycles, and `logfire.variables_push(strict=True)` refuses to apply an invalid configuration. The walk covers the *full* reachable graph (local code defaults and server-stored label values), so a missing reference (or a cycle whose midpoint is a server-only variable) is caught before it ever ships.

A cycle (or depth overflow) is always a structural failure. When it occurs while composing a stored value, resolution falls back to the code default; the example below puts the cycle in the code defaults themselves, so resolution can only return the raw, uncomposed default:

```python
import warnings

import logfire
from logfire.variables import VariableCompositionError

logfire.configure()

# A pair of variables that reference each other. Push-time validation
# would catch this; we register them here just to show what the runtime
# guard does when it does have to step in.
left = logfire.var('cycle_left', type=str, default='@{cycle_right}@')
logfire.var('cycle_right', type=str, default='@{cycle_left}@')

with warnings.catch_warnings(record=True) as caught:
    warnings.simplefilter('always')
    with left.get() as resolved:
        # `resolved.reason` is `'other_error'` because composition failed,
        # and `resolved.exception` is a `VariableCompositionError` (or a
        # subclass like `VariableCompositionCycleError` for cycles).
        print(resolved.reason, isinstance(resolved.exception, VariableCompositionError))
        #> other_error True
    print(any('composition failed' in str(w.message) for w in caught))
    #> True
```
