# Agent Control

Agent Control turns one AI agent's configuration into something you edit in Logfire instead of in your source code. The instructions you send the model, which model you send them to, the model settings you send with them, and the descriptions your tools show the model all become editable from the Logfire UI: versioned, labelled, rolled out to a slice of traffic, and rolled back as one unit, without a redeploy.

Everything you don't change in Logfire keeps doing exactly what your code says, and removing a change there puts that piece back. There is no third state.

Agent Control is built on [managed variables](managed-variables/index.md), and inherits the whole model: versions, labels, rollouts, targeting, and a span for every resolution. What it adds is a *shape*. A managed variable can hold anything; an Agent Control variable holds one agreed structure, `AgentConfig`, that the Logfire UI knows how to render as a prompt editor rather than a JSON box, and that every Logfire SDK reads the same way.

!!! note "Install the agent-control extra"
    Agent Control requires the `logfire[agent-control]` extra, which pulls in managed variables and `pydantic`.

    ```bash
    pip install 'logfire[agent-control]'
    ```

## What this page covers

`logfire.agent_control` is the **framework-neutral core**. It assumes nothing about how you built your agent: it owns the config contract, the Logfire variable each agent's config lives in, and the pure functions that say what a published value *does* to a request.

Eventually most people will never call it directly: you will install the adapter for the agent framework you already use, and it will call this core for you. None of those [adapters](#framework-adapters) has shipped yet, so for now driving Agent Control means writing the per-request hook yourself, which [Writing an adapter](#writing-an-adapter) walks through. Read on for that, for exactly what a published value can and cannot do to your agent, or if your agent is hand-rolled.

## Quick start

An `AgentControl` names one agent and reads its config:

```python
import logfire
from logfire.agent_control import AgentControl, Block, apply_instructions

logfire.configure()

control = AgentControl('checkout-assistant', label='production')

# The instructions your code defines, each one addressable by a stable id.
blocks = [Block('You are a concise checkout assistant.', id='agent')]

with control.resolution() as resolution:
    # Inside this block, every span carries the label and version that produced it.
    if resolution.config is not None:
        blocks = apply_instructions(blocks, resolution.config).blocks
    print('\n\n'.join(block.text for block in blocks))
    #> You are a concise checkout assistant.
```

With nothing published, `resolution.config` is `None` and the agent runs exactly as written, which is also what happens when Logfire is unreachable or the stored value is one this release can't parse. Publish an override for the `agent` block in the Logfire UI and the same code sends the published text instead.

The agent's name is explicit on purpose. The config is keyed on it, so a name inferred from a class or a Python variable would silently point the agent at a different config the day someone renames it. `AgentControl('checkout-assistant')` backs the agent with the Logfire variable `agent__checkout_assistant`.

## The config shape

Every section is optional, and an absent one means "leave this to code". Here is a published value with every section in play:

```json
{
  "instructions": [
    "Escalate anything over $500 to a human.",
    { "id": "agent", "instructions": "You are a refund specialist." },
    { "id": "agent:refunds", "instructions": "Confirm the order total." },
    { "id": "toolset:legacy_crm" }
  ],
  "model": "anthropic:claude-sonnet-4-5",
  "settings": { "temperature": 0.4, "max_tokens": 2048, "thinking": "high" },
  "tool_definitions": [
    {
      "name": "get_weather",
      "new_name": "lookup_weather",
      "description": "Look up the current weather for a city.",
      "parameters": { "city": { "description": "City name, e.g. 'London'" } }
    },
    { "name": "search", "toolset": "crm", "description": "Search CRM records." }
  ]
}
```

Reading the `instructions` entries in order:

- A **bare string** has no `id`, so it is a new block added to the agent's instructions.
- An entry with an **`id` and text** rewrites the block your code registered under that id. `agent` is the one id the contract reserves: the agent's own prompt.
- An entry with an **`id` and no text** removes that block.

A bare `"instructions": "text"` is also valid and means one added block, so a hand-written value gets the short form.

One kind of block is deliberately out of reach: a **dynamic** block, one the agent recomputes on every request from whatever that run carries — today's date, the signed-in user, a retrieved document. Replacing it would pin one request's rendering forever and removing it would delete the computation, and either way the block stops doing what it was written to do, with nothing in the published value to say so. Addressing one is refused rather than applied, and reported as `dynamic-id` under [`on_unmatched`](#writing-an-adapter). Adding blocks and editing the static ones around it still works.

Ordering follows from the same concern. A replaced block keeps its position and its static/dynamic side, and an added block lands at the end of the leading run of static blocks — after the last static block the agent assembles, before the first dynamic one. That is where a published addition is last in the prompt as written and still inside the prefix a provider can cache, so managing an agent's instructions does not cost you the prompt cache on every request.

`settings` names the eleven canonical keys every framework has a knob for: `max_tokens`, `temperature`, `top_p`, `top_k`, `seed`, `presence_penalty`, `frequency_penalty`, `parallel_tool_calls`, `timeout`, `stop_sequences`, and `thinking`. Provider-specific settings and things like `extra_headers` stay in code. They are not part of the contract, and the config is stored where everyone in the project can read it.

`tool_definitions` changes only what the model is *told* about a tool: its name and description, and its parameters' descriptions. Parameter names, types, requiredness, validation, and the implementation stay code-defined.

### The baseline

A **baseline** is the same shape, describing your code rather than changing it. Your adapter publishes it as the variable's `example`, and the Logfire editor renders it as the code side to diff published values against. It is what turns a blank form into "here is your prompt, block by block; change this one".

```json
{
  "instructions": [
    { "id": "agent", "instructions": "You are a concise checkout assistant.", "dynamic": false },
    { "id": "agent:refunds", "instructions": "Always confirm the order total.", "dynamic": false },
    { "id": "agent:today", "dynamic": true }
  ],
  "model": "anthropic:claude-sonnet-4-5",
  "settings": { "temperature": 0.1 },
  "tool_definitions": [
    {
      "name": "get_weather",
      "description": "Get the current weather for a city.",
      "parameters": { "city": { "description": "City to look up." }, "units": {} },
      "toolset": "<agent>"
    }
  ]
}
```

Note the third instruction block: it carries its id and `dynamic: true`, and no text. Its text is one request's rendering of whatever that run carried, so publishing it would leak one run's data into a variable the whole project can read. Note also the `units` parameter with an empty entry: an undocumented parameter is exactly the one somebody wants to describe from Logfire, so the baseline lists every top-level parameter, documented or not.

## Writing an adapter

An adapter does five things. Nothing else in `logfire.agent_control` is required, and nothing else is public.

**1. Name the agent's config.** `AgentControl('checkout-assistant', label='production')`. The name you pass is kept verbatim for display and normalized for the variable key; see [Agent name to variable key](#agent-name-to-variable-key).

**2. Publish the baseline.** `build_baseline(instructions=..., model=..., settings=..., tools=...)` describes the agent as written, and `control.publish_baseline(...)` stores it, creating the variable with the shared JSON schema if Logfire doesn't have it yet. It runs at most once per process, off the calling thread, and can never fail a request. Say whether you are publishing the agent as written or one request you observed, with `source='code'` or `source='observed'`.

**3. Read the published value.** `with control.resolution() as resolution:` resolves once for a run and yields a `Resolution`: `config`, plus the `label`, `version`, and `reason` it came from. Inside that block the resolved label and version ride as OpenTelemetry baggage, so every span and log the run emits says which published version produced it. `control.resolve()` is the one-shot sugar for a framework that has nowhere to hold a context open.

**4. Apply it, in the framework's own per-request hook.**

- `apply_instructions(blocks, config)` takes the `Block`s the agent is about to send and returns `.blocks`, with published text swapped in, removed, or added, plus `.unapplied`.
- `apply_tool_definitions(tools, config)` takes the `ToolDef`s the agent is about to advertise and returns `.tools` with managed names and descriptions applied, `.routes` mapping advertised name back to code name, `.forward` and `.reverse` for a framework where a bare name is not an identity, and `.unapplied`. Pass `reserved={...}` to keep names the adapter needs for itself out of reach of a rename.
- `apply_settings(config)` returns the settings patch to merge over the agent's own. `merge_settings(code, published, run_explicit)` is that merge, in the contract's order; `canonical_settings(settings)` is the reverse, for a baseline.

**5. Report what reached nothing.** Every apply function takes `on_unmatched`: `'warn'` (the default, once per process), `'error'`, or `'ignore'`. An instruction `id` no block carries, a tool override no tool matches, a rename that collides, a settings key your framework can't apply: each is a place where Logfire shows one thing and the agent does another, and the adapter is the only thing that can see it.

Here is an adapter end to end, for an imaginary framework whose agent has one prompt string, a list of tools, a hook around each run, and a hook before each model request:

```python skip="true"
from contextvars import ContextVar

from logfire.agent_control import (
    AgentControl,
    Block,
    ToolDef,
    apply_instructions,
    apply_settings,
    apply_tool_definitions,
    build_baseline,
    canonical_settings,
    merge_settings,
)


def agent_control(agent, name, *, label=None):
    """Make `agent` configurable from Logfire, and return it."""
    control = AgentControl(name, label=label)
    published = ContextVar('agent_control_config', default=None)

    def around_run(run):
        # One resolution per run, held for the whole of it: every span inside carries the label and
        # version that produced it, and a value published mid-run applies to the next one.
        with control.resolution() as resolution:
            token = published.set(resolution.config)
            try:
                return run()
            finally:
                published.reset(token)

    def before_request(request):
        blocks = [Block(request.prompt, id='agent')]
        tools = [ToolDef(t.name, t.description, t.parameters_json_schema) for t in request.tools]
        control.publish_baseline(
            build_baseline(
                # The baseline is published where every project member can read it, and this
                # framework hands the adapter a *rendered* prompt rather than the code that produced
                # it -- so the block goes in as dynamic, which says that it exists without saying
                # what this one request made it say. `build_baseline` drops the text for it.
                instructions=[Block(request.prompt, id='agent', dynamic=True)],
                model=agent.model,
                settings=canonical_settings(agent.settings),
                tools=tools,
            ),
            # This framework's prompt and tool list are only knowable once a request is assembled,
            # so what is published describes *this* request rather than the code.
            source='observed',
        )

        config = published.get()
        if config is None:
            return request  # Nothing published: the agent runs exactly as written.

        # Every helper takes the policy the control was built with, so `on_unmatched='error'` really
        # does fail and `'ignore'` really is silent, wherever the mismatch turns up.
        policy = control.on_unmatched
        applied_blocks = apply_instructions(blocks, config, on_unmatched=policy).blocks
        request.prompt = '\n\n'.join(block.text for block in applied_blocks)
        applied = apply_tool_definitions(tools, config, on_unmatched=policy, reserved=request.provider_tool_names)
        by_name = {tool.name: tool for tool in request.tools}
        request.tools = [by_name[applied.routes[t.name]].with_definition(t) for t in applied.tools]
        request.routes = applied.routes  # The dispatcher maps a name the model called back with this.
        # `supported` names the canonical keys this framework has a knob for; the rest are reported.
        patch = apply_settings(config, supported=agent.supported_settings, on_unmatched=policy)
        # Published settings beat the agent's own; the ones this call passed explicitly beat both.
        merged = merge_settings(agent.settings, patch, request.explicit_settings)
        request.settings = merged.settings
        if config.model is not None:
            request.model = config.model
        return request

    agent.around_run(around_run)
    agent.before_request(before_request)
    return agent
```

Two things every adapter has to decide for its framework, because frameworks genuinely differ: whether a renamed tool reaches your implementation under its old name or its new one (`routes` gives you the mapping either way, and history the model already saw may need remapping too), and how the canonical `provider:model` string maps to its own model convention.

## Contract

Three things have to give the same answer in every language that implements Agent Control, because a Logfire project is shared and the SDKs are not. They are specified here, and pinned by conformance vectors that this SDK and the TypeScript SDK both run against; the canonical copy of those vectors lives in this repository at `tests/agent_control/spec/`.

### Agent name to variable key

An agent's config lives at `agent__<key>`, where the key is derived from the agent's name by one rule:

1. Trim leading and trailing whitespace.
2. Lowercase.
3. Replace every character outside `[a-z0-9_]` with `_`.
4. Collapse runs of `_` into one.
5. Strip `_` from both ends.

A name with nothing left after that (whitespace, punctuation, or a script with no ASCII in it) is refused rather than turned into a variable. A name that already starts with `agent__` is a mistake you're warned about, not a doubled prefix.

`AgentControl.name` is the **display name**, kept exactly as you passed it (trimmed), because it is what a person recognizes the agent by and what telemetry shows. `AgentControl.variable_name` is the **variable key**, which is the rule above. They are deliberately different things: you can improve how a name reads without moving the agent onto a different config, as long as it still normalizes to the same key.

Lowercasing is the lossy step, and it is the point. The rule is the one the Logfire UI applies, so an agent called `Checkout Assistant` in one SDK and `checkout-assistant` in another land on the one config the UI shows for them. It is lossy in the other direction as well: two genuinely different agents whose names differ only in punctuation or case share a config. Give them distinct names when that is not what you want.

### The unit of resolution

Resolve **once per run** where the framework has a run seam, something that brackets a whole agent run, and hold that one `Resolution` for the whole of it. Every span of the run then agrees on the version that produced it, and a value published mid-run takes effect on the next run rather than halfway through this one.

Where the framework offers only a per-model-request hook, resolution is **per model request**, and a rollout can legitimately land differently on two requests of one run. Both are supportable. What is not supportable is an adapter that resolves twice in one request, because a publish or a probabilistic rollout between the two sends prompt A with model B while telemetry attributes the request to B alone.

A framework that resolves in one place and calls the model in another carries the `Resolution` in its own state and wraps each later block in `with use_resolution(resolution):`, which both puts the same label and version back on that block's spans and makes `control.current_resolution()` answer with that one resolution for the whole block:

```python skip="true"
from logfire.agent_control import use_resolution

# In the node that starts the run:
with control.resolution() as resolution:
    state.resolution = resolution

# In every later node, however far from the first:
with use_resolution(state.resolution):
    config = control.current_resolution().config
```

### What a baseline is

A baseline is a *description of the agent*, published as the variable's `example` and rendered by the Logfire editor as the thing a managed value is layered onto. It is never resolved and never applied. Because it is read by every member of the project and treated as the truth about the code, it owes the editor exactly these things:

- **Stable ids.** Every block the editor may offer an override for carries the `id` that addresses it, and that id is stable across requests and deploys. A positional id that moves when someone reorders their prompt sources is not stable.
- **A dynamic block carries `{id, dynamic: true}` and never text.** Its text is one request's rendering of whatever that run carried (a tenant name, a user id, a retrieved document), so publishing it leaks one run's data into a shared variable and invites an override that pins it forever. A dynamic block with nothing to key it on is left out entirely, since the editor could neither show nor address it.
- **Every top-level parameter of every tool is listed**, with `description` when the code has one and an empty entry when it does not.
- **Settings are canonical keys with validated values.** Everything else, including provider-specific keys, `extra_headers`, and `extra_body`, stays in code, because that is where authorization headers and signed bodies live. `canonical_settings` is that filter.
- **`toolset` is present when known and absent when not.** Never guessed: an override narrowed to a toolset only works if the value the editor shows is the value the override can be written against.
- **Unrepresentable values are omitted and reported, never approximated.** A reasoning effort a framework spells `'max'` is not `'xhigh'`, and a timeout outside the representable range is not the nearest one that fits.
- **A code baseline is not a first-request observation**, and the adapter says which it is publishing with `publish_baseline(..., source='code' | 'observed')`.

### Parsing a published value

Leniency is **per section**: a section, entry, or setting this release can't make sense of costs only itself, and everything around it still applies. A value that fails validation outright falls back through Logfire's resolution to the code-defined agent *in its entirety*, which is what makes that rule load-bearing rather than polite. Four consequences worth stating, because they are where two independent implementations drift:

- **An invalid `model` drops only `model`.** The section is the unit because `model` has no entries to degrade one at a time.
- **The instruction budget is charged to surviving entries only.** An entry dropped for being malformed adds nothing to the request, so charging it would let one bad entry shrink the budget for the good ones.
- **Text length is counted in Unicode code points**, so an emoji costs the same in every SDK.
- **`''` is never a value.** Not "no model", not "no instructions", not "no name": it is a field someone left half-filled, and `null` already means "leave this to code".

Values are read **strictly** with respect to JSON types: `1` is a valid `temperature` because JSON writes `1` for `1.0`, while `"0.4"` is a string where the stored schema says `number`, and is dropped. Code-side values going into a baseline are read leniently instead, because they come from a framework's own objects rather than from the wire.

## What it guarantees

**Nothing published can crash your agent.** An unreachable Logfire, a missing value, or one this release can't parse leaves `resolve()` returning `None`. Beyond that, a value the contract can't act on costs only the piece containing it (one setting, one tool override, one block) and warns once per process, so one unfamiliar key from a newer UI never silently un-manages the rest.

**Overrides never move the prompt-cache boundary.** A replaced block keeps its position and its static/dynamic side, and an added block lands at the end of the leading run of static blocks, so published text stays inside the prefix a provider can cache.

**Only what the model is told about a tool is editable.** A rename that collides with another advertised name, or with a name the adapter reserved for a handoff or a provider tool, is dropped under `on_unmatched` while that override's other patches still apply, so every tool keeps a name the model can call.

**Publishing the baseline can lose a concurrent UI publish.** A missing variable is *created* rather than overwritten, an existing one is re-read immediately before the write, the write is skipped when that fresh read already carries this `example`, and the whole thing runs at most once per process per variable. What is left is one HTTP round trip: a value saved in the Logfire UI between that read returning and the write landing is overwritten by the older state. A deployment that can't tolerate that window passes `publish_baseline=False` and creates the variable in the UI.

**The stored JSON schema is a contract, not a derived artifact.** `AGENT_CONFIG_JSON_SCHEMA` is maintained by hand and pinned by `SCHEMA_SHA256`, which the TypeScript SDK and the Logfire UI pin identically: whichever side creates a variable first is the one whose schema is persisted, and the Logfire backend validates every write against it.

## Framework adapters

You normally use Agent Control through an adapter for the framework you already build with. Each is this core plus that framework's own per-request hook, typically under fifty lines.

!!! note "The adapters are not released yet"
    None of the adapters below ships today. Each lands as its own change on top of this core, and this section will link to each one as it becomes available. Until then, the way to drive Agent Control is to write the per-request hook yourself, as [Writing an adapter](#writing-an-adapter) describes.

| Framework | Language |
|---|---|
| OpenAI Agents SDK | Python |
| LangChain | Python |
| Google ADK | Python |
| Claude Agent SDK | Python |
| LiveKit Agents | Python |
| Vercel AI SDK | TypeScript |
| Codex SDK | TypeScript |
| Mastra | TypeScript |

For [Pydantic AI](https://pydantic.dev/docs/ai/), Agent Control ships as a capability in [`pydantic-ai-harness`](https://github.com/pydantic/pydantic-ai-harness) rather than as a separate adapter, because Pydantic AI already has the seams this core wants.

## Next steps

- [Managed Variables](managed-variables/index.md): the versions, labels, rollouts, and targeting that Agent Control is built on.
- [Managing Variables in the Logfire UI](managed-variables/ui.md): where you edit a published value.
- [A/B Testing](managed-variables/ab-testing.md): splitting traffic between two configs and comparing them in traces.
