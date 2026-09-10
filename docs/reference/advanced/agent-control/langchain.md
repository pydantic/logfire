# Agent Control for LangChain

Agent Control makes a LangChain agent's **instructions, model, model settings, and tool descriptions** editable from the Logfire UI: versioned, labelled, rolled out to a slice of traffic, and rolled back as one unit, without a redeploy. Everything you don't change in Logfire keeps doing exactly what your code says, and removing a change there puts that piece back.

For LangChain's [`create_agent`](https://docs.langchain.com/oss/python/langchain/agents) it is one `AgentMiddleware`. This page is the adapter; [Agent Control](index.md) is the contract underneath it, and worth reading first for what a published value can and cannot do to any agent.

!!! note "Install the agent-control-langchain extra"
    ```bash
    pip install 'logfire[agent-control-langchain]'
    ```

    It pulls in the framework-neutral core, `pydantic`, and LangChain itself — but not a model integration, which in LangChain is always a package of its own: the quick start below also needs `pip install langchain-anthropic`, and a published `model` naming a provider whose integration is not installed is reported rather than applied.

    You still need a Logfire project: a `logfire.configure()` with a token that can read variables, and one that can write them if you want the baseline published from your code rather than created by hand in the UI.

## Quick start

One middleware, **last** in the list:

```python skip-run="true" skip-reason="external-connection"
from langchain.agents import create_agent
from langchain_core.tools import tool

import logfire
from logfire.agent_control.langchain import agent_control

logfire.configure()


@tool(parse_docstring=True)
def get_weather(city: str) -> str:
    """Get the current weather for a city.

    Args:
        city: The city to look up.
    """
    return f'sunny in {city}'


agent = create_agent(
    'anthropic:claude-haiku-4-5',
    tools=[get_weather],
    name='checkout_assistant',
    middleware=[
        agent_control(
            instructions={
                'role': 'You are a concise checkout assistant.',
                'refunds': 'Always confirm the order total before refunding.',
            },
            label='production',
        )
    ],
)

result = agent.invoke({'messages': [{'role': 'user', 'content': "What's the weather in Paris?"}]})
print(result['messages'][-1].text)
```

Three things in that snippet are load-bearing.

**Last in `middleware=[...]`.** LangChain composes `wrap_model_call` first-in-list as the *outermost* layer, so being last makes this the innermost one: the only position that sees the request every other middleware has finished assembling, and the only one whose changes nothing downstream can overwrite.

**`name=` on `create_agent` is the config's key.** The agent's config lives in the Logfire variable `agent__checkout_assistant`, and `name` is also what Logfire shows the agent as in traces, so the two line up. An agent created without a `name` is called `LangGraph`, which is nobody's agent, so the middleware raises rather than guess. If the agent must stay unnamed, name the middleware instead: `agent_control(name='checkout_assistant')`.

The name is read off each run, because LangChain merges a run's own `metadata` over the one `create_agent` bound. So `agent.invoke(..., {'metadata': {'lc_agent_name': 'other'}})` renames the agent for that run — in Logfire's traces as well, since the instrumentation names the agent's spans from the same value — and the config follows it, for that run and no other: the name rides in the run's own state beside its resolution, so two concurrent runs of one agent under two names never read or publish through each other's. Pass `agent_control(name=...)` when the config's key must not be something a caller can move; do that in particular if your `metadata` is assembled from anything a request supplied.

**The prompt is declared on the middleware**, not on `create_agent`. That is the one-line diff from a plain string:

```diff
-    system_prompt='You are a concise checkout assistant.',
     name='checkout_assistant',
-    middleware=[agent_control(label='production')],
+    middleware=[agent_control(instructions={'role': 'You are a concise checkout assistant.'}, label='production')],
```

and it is what makes the prompt editable, block by block. Each key is a block id (`system:role`, `system:refunds`), each value is its text, and each can be rewritten or removed in Logfire on its own. A value can also be a callable taking the `ModelRequest` — `lambda request: f'Today is {date.today()}.'` — for a block worked out per request: those are sent after the fixed ones, so they never move the prefix a provider can cache, and they are published as seams rather than as text.

The middleware assembles that prompt onto a request that has none, so the agent must not also have a `system_prompt` (nor a middleware that writes one); if it does, the middleware raises rather than pick one. A prompt kept on `create_agent` still works and is still applied to, but only the blocks of a `SystemMessage` content list that name themselves with an `id` are editable:

```python skip-run="true" skip-reason="external-connection"
from langchain.agents import create_agent
from langchain_core.messages import SystemMessage

from logfire.agent_control.langchain import agent_control

agent = create_agent(
    'anthropic:claude-haiku-4-5',
    name='checkout_assistant',
    system_prompt=SystemMessage(
        content=[{'type': 'text', 'text': 'You are a concise checkout assistant.', 'id': 'role'}]
    ),
    middleware=[agent_control(label='production')],
)
```

That is the difference an `id` makes. A `ModelRequest` carries no provenance: the text `create_agent` was written with and text a `@dynamic_prompt` middleware computed from this run's tenant, user, or retrieved documents arrive here as the same string. Declaring the prompt on the middleware settles it by construction, and an `id` on a block you keep on `create_agent` is the same declaration by hand. Anything else — a plain `system_prompt='...'` string included — is a seam: published as an id with no text, and refused as an override target.

## `agent_control(...)`

| Argument | Meaning |
|---|---|
| `name` | The agent's name, keyed as the Logfire variable `agent__<name>`. Defaults to `create_agent(name=...)`, read off the run. |
| `instructions` | The agent's prompt as `{block id: text or callable}`, instead of `create_agent(system_prompt=...)`. Assembled onto every request, in declaration order, fixed blocks first. |
| `label` | The label to resolve, such as `'production'`. `None` lets the variable's own targeting rules and rollout choose. |
| `on_unmatched` | What to do about a published entry that reaches nothing here: `'warn'` (default, once per process), `'error'` (fails the request), `'ignore'`. |
| `publish_baseline` | Whether to publish what the agent sends as the variable's `example`, which also creates the variable. Default `True`; set `False` for a read-only token. |
| `logfire_instance` | The Logfire instance to resolve and publish through. Defaults to the global one. |

It returns an `AgentControlMiddleware` — the type is exported for annotations and subclasses — and that is all it builds. Your agent, your model object, and your tool objects are never mutated: what a published config changes is the `ModelRequest` a model is about to be sent, per request, by returning copies. `AgentControlMiddleware(...)` takes the same keyword arguments if you would rather construct it directly.

## What becomes editable

Support is per row: **yes** means it works as written, **conditional** means the row's own conditions decide, **no** means it is not managed at all.

### Instructions

| Source | Block id | Support | Conditions, and what an override that misses does |
|---|---|---|---|
| A string in `agent_control(instructions={...})` | `system:<key>` | yes | Replaceable and removable on its own. Code-side by construction: the middleware assembled the prompt out of what your code passed it. |
| A callable in `agent_control(instructions={...})` | `system:<key>` | no | Called with the `ModelRequest` on every request, so it is a seam: published with no text, and an override addressing it is reported under `on_unmatched` and not applied. Sent after the fixed blocks. |
| A `SystemMessage` content block with an `id` | `system:<id>` | yes | Replaceable and removable on its own. Your `id` is what declares the block code-side; the id is stripped before the request goes out, since OpenAI forwards content blocks verbatim. |
| A `system_prompt='...'` string | `system` | no | Published as a seam with no text, and an override addressing it is reported under `on_unmatched` and not applied: nothing here can tell it from a prompt a `@dynamic_prompt` middleware computed for this one request. Move it into `instructions=`, or give its blocks `id`s, to make it editable. |
| A content block with no `id` of its own | `system:<index>` | no | Same seam, and its positional id would move the day you insert a paragraph above it. |
| Non-text content (an image, a provider block) | — | no | Carried through untouched and offered to nobody. |
| An added block (an entry with no `id`) | — | yes | Lands at the end of the *leading run* of blocks your code declared — after the last one before the first seam or callable, not after the last one overall. Declare `a`, a seam, and `b`, and the addition goes between `a` and the seam. That is where the contract keeps managed text: inside the prefix a provider can cache. |
| An agent with no system prompt at all | — | yes | An added block becomes the whole system message. |

### Model

| Canonical field | Runtime mapping | Support | Conditions, and what an override that misses does |
|---|---|---|---|
| `model` | `init_chat_model('provider:model')` | conditional | Published as `provider:model`, which is LangChain's own spelling for every provider but five; those are translated (`google`, `google-cloud`, `mistral`, `azure`, `bedrock`), and a string with no `:` is handed to LangChain to infer. The integration package has to be installed: a model LangChain cannot build is reported and the request keeps the model it has. A request that already carries a model *another middleware* chose is left alone and reported; see [Resolution, baseline, and precedence](#resolution-baseline-and-precedence). |

The contract's ids for Google are `google` (the Gemini API) and `google-cloud` (Vertex). `google-gla` and `google-vertex`, which those two were called before they were renamed, are still accepted from a published value, so a config that predates the rename keeps working; nothing this adapter publishes uses them.

### Model settings

Applied only when the model's own integration declares a field (or a field alias) for the setting, which is read off the model class rather than from a table of providers. A canonical key this model has no knob for is reported under `on_unmatched` rather than sent to an API that would reject it.

| Canonical field | Runtime mapping | Support | Conditions, and what an override that misses does |
|---|---|---|---|
| `max_tokens` | `max_tokens` | conditional | Applied when the model class declares it (OpenAI's and Anthropic's do). |
| `temperature` | `temperature` | conditional | As above. |
| `top_p` | `top_p` | conditional | As above. |
| `top_k` | `top_k` | conditional | Anthropic has it; OpenAI does not, so a `top_k` published against an OpenAI agent is reported. |
| `seed` | `seed` | conditional | OpenAI has it; Anthropic does not, and a `seed` published against it is reported. |
| `presence_penalty` | `presence_penalty` | conditional | OpenAI has it; Anthropic does not. |
| `frequency_penalty` | `frequency_penalty` | conditional | OpenAI has it; Anthropic does not. |
| `stop_sequences` | `stop` or `stop_sequences` | conditional | Whichever name the integration declares; both send the provider's own spelling. |
| `timeout` | `timeout` | conditional | The alias of `request_timeout` (OpenAI) and `default_request_timeout` (Anthropic), in seconds. It is the HTTP deadline and is not part of the request body. A value the contract cannot represent is reported by the core and not applied. |
| `thinking` | `reasoning_effort` | conditional | As an effort level (`'low'`, `'high'`, …). A bare `true`/`false` is reported, not guessed at: OpenAI's reasoning models always reason, and Anthropic's `thinking` wants a shape that depends on the model generation. |
| `parallel_tool_calls` | `bind_tools(parallel_tool_calls=...)` | conditional | Applied when the model's `bind_tools()` names the parameter *and* the request has tools; with no tools `create_agent` calls `bind()`, which sends the key straight to a provider that rejects it. |

Anything else — `extra_headers`, provider-specific constructor fields, `model_kwargs` — stays in code. It is not part of the contract, and the baseline is published where everyone in your Logfire project can read it.

!!! warning "A setting the integration accepts is not always one the model accepts"
    "Conditional" above is answered by the model *class*, which is as far as anything here can see. The provider gets the last word, per model, and there is nothing to report in advance: a published setting a model generation refuses fails that request, exactly as the same value passed in code would. Recorded against the real APIs:

    - **`thinking` needs a model with an effort control.** `claude-haiku-4-5` answers `This model does not support the effort parameter`; `claude-fable-5-1` takes it. On OpenAI, `reasoning_effort` is refused outright by a non-reasoning model such as `gpt-4.1-nano`, and refused *alongside function tools* by `gpt-5.4-nano` on `/v1/chat/completions`.
    - **`stop_sequences` is not universal on OpenAI.** `gpt-4.1-nano` takes `stop`; `gpt-5.4-nano` answers `Unsupported parameter: 'stop' is not supported with this model`.
    - **Anthropic refuses `temperature` and `top_p` together**, whichever of them your code set and whichever Logfire published.

    Publish a setting against the model you are actually running, and roll it out to a slice of traffic first — which is what Agent Control is for.

### Tools

| Source | Runtime mapping | Support | Conditions, and what an override that misses does |
|---|---|---|---|
| A tool's name | advertised name; calls translated back | yes | See [Renamed tools](#renamed-tools-from-your-codes-side). A rename onto a name another tool already answers to is dropped and reported, so every tool keeps a name the model can call. |
| A tool's description | advertised description | yes | An override that says nothing about the description leaves the code's own, empty or not. |
| A parameter's description | that property's `description` | yes | A patch naming a parameter the tool does not have, or one whose schema has nothing to describe, is reported. |
| Parameter names, types, requiredness, validation, implementation | — | no | Deliberately: only what the model is *told* about a tool is managed, so nothing published can change what your code receives. |
| Which tools exist | — | no | Agent Control patches the tools your agent already advertises; it never adds or removes one. |
| `toolset` on an override | — | no | LangChain has no notion of a toolset, so no tool reports one and an override that sets one matches nothing — and says so. |
| A provider built-in (a `dict` in `tools=`, such as web search) | — | no | No code-side definition to patch and no implementation to route a rename back to. Passed through untouched, and not reserved: a rename onto its name is not detected as a collision. |
| A structured-output tool (`response_format`) | — | no | LangChain appends it *after* middleware run and validates it by name. |

## Resolution, baseline, and precedence

**The config is read once per run**, in `before_agent`, and that one version is applied to every model request and tool call in the run. Publishing something mid-run takes effect on the next run. The resolution rides in the agent's private graph state, so it survives a checkpointer, and every **model request and tool call** re-enters it: those spans, and the ones your model and tools emit inside them, carry the label and version that produced them. Spans from graph nodes outside those two hooks do not — a middleware cannot hold a context open across the nodes that come after it.

**The baseline is one observed request, and says so.** `create_agent` keeps the prompt, the model and the tool list in a closure the compiled agent does not expose, so the earliest anything can be read here is the first request. It is published as the variable's `example` with `source='observed'`, which is what tells the Logfire editor that the model, settings and tools in it are the ones *that* request carried rather than a description of your code — and blocks whose text this middleware cannot attribute to your code go up as seams with no text. Pass `publish_baseline=False` if the token is intentionally read-only.

**Precedence is code, then published, then this run.** A published `settings` value beats what the model was constructed with, and a `model_settings` entry another middleware set for this one request beats both — which is also where Anthropic prompt-cache directives arrive. A published setting losing to a per-request one is reported under `on_unmatched`: it is the contract working, but it is also a value someone can change in Logfire to no effect on every request, and nothing else would say why. A published `model` replaces the model the agent was *built* with; a request that arrives carrying a different one got it from a middleware ahead of this one — a fallback after an error, a choice made from the run's own state — and that choice stands, with the published `model` reported as not applied. The model the agent was built with is learned from the first request that reaches this middleware, so an agent whose model is chosen dynamically on *every* request is one this cannot see through: the first choice it observes is the one it will treat as the code's.

A published `model` also carries the code model's canonical settings across, since the replacement is a fresh instance with its class's defaults; a setting the new provider has no kwarg for does not move.

Prompt caching is left where your code put it. A string prompt stays a string and a list of blocks stays a list, each block keeping its own `cache_control`; added text lands inside the leading run of declared blocks; tool order never changes. (Renaming or rewording a tool does change the tools prefix, and misses the cache once per publish, as it would anywhere.)

## Renamed tools, from your code's side

Rename `get_weather` to `lookup_weather` in Logfire and the model is shown `lookup_weather`. Everything on your side of that boundary keeps the name your code gave the tool: the call in the `AIMessage`, the `ToolNode` that dispatches it, a `wrap_tool_call` in any other middleware, the `ToolMessage` it produces, the state a checkpointer writes down, and the trace. The reply is translated back before it becomes any of those, and the history is translated forward again on the way out, so the model always sees the names it was shown.

That is also what makes a thread outlive a change: resume a conversation after the rename has been changed or withdrawn and its stored calls are replayed under whatever the model is being shown now, rather than naming a tool that no longer exists.

## Known limits

- **Put the middleware last.** Anything after it can overwrite what it applied, and it will not see what that middleware contributed.
- **A prompt this middleware cannot attribute to your code is not editable.** Declare it with `instructions=`, or give the block an `id`; there is no way to tell an undeclared string from one computed for this request.
- **`instructions=` is the whole prompt.** It is assembled onto a request that carries none, and an agent that also has a `system_prompt` (or a middleware that writes one) raises rather than have this middleware choose between two prompts.
- **A model chosen dynamically on every request** hides the code's model from this middleware, so a published `model` may be reported as not applied. Publish the model in Logfire *or* choose it in a middleware, not both.
- **An inferred name is only as trustworthy as your `metadata`.** A run can rename the agent, and the config follows. Pass `agent_control(name=...)` when that matters.
- **A setting can be right for the integration and wrong for the model.** See the warning under [Model settings](#model-settings).
- **No toolsets.** LangChain has no notion of one, so the baseline reports no `toolset` for any tool and an override that sets `toolset` matches nothing (and says so).
- **`create_agent` only.** A hand-written LangGraph graph has no per-request hook to apply a config in, and `langgraph.prebuilt.create_react_agent` is deprecated: its hooks never see the bound model.
- **Publishing the baseline can lose a concurrent UI publish.** The client side narrows that window as far as it can — see [What it guarantees](index.md#what-it-guarantees) — but a value saved in the UI during the write can be overwritten. A deployment that cannot tolerate that sets `publish_baseline=False`.

An unreachable Logfire, nothing published, or a value this release cannot parse all mean the same thing: the agent runs exactly as written. Beyond that, a value the contract cannot act on costs only the piece containing it — one setting, one tool, one block — and is reported under `on_unmatched`.

## Next steps

- [Agent Control](index.md): the config shape every adapter reads, and what a published value can and cannot do.
- [Managed Variables](../managed-variables/index.md): the versions, labels, rollouts, and targeting Agent Control is built on.
- [Managing Variables in the Logfire UI](../managed-variables/ui.md): where you edit a published value.
