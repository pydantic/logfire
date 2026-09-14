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

A **baseline** is the same shape, describing your code rather than changing it. Your adapter reports it to Logfire, which renders it as the code side to diff published values against. It is what turns a blank form into "here is your prompt, block by block; change this one" — and what an agent that has no config yet is registered by.

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

Note the third instruction block: it carries its id and `dynamic: true`, and no text. Its text is one request's rendering of whatever that run carried, so reporting it would leak one run's data into an artifact the whole project can read. Note also the `units` parameter with an empty entry: an undocumented parameter is exactly the one somebody wants to describe from Logfire, so the baseline lists every top-level parameter, documented or not.

### Publication

A baseline quotes your agent's own prompt and tool descriptions into a Logfire project everyone on your team can read. That is the point — it is what lets the editor open on your prompt instead of on a blank form — and it is also something a team should be able to turn down without giving up Agent Control. `AgentControl(report_baseline=...)` is that control, and it has three settings:

| | What leaves your process | What the editor can do |
|---|---|---|
| `'text'` | The whole baseline: instruction text, tool and parameter descriptions | Everything |
| `'structure'` | Every **seam** and no prose: instruction ids and their `dynamic` flags, tool names, toolsets, parameter names | Override every block and every tool, without showing you what the code says |
| `'off'` | No baseline at all | Nothing — the agent still appears on the Agent Control page, but there's nothing to build a config from |

`'structure'` is the one to reach for if your prompts can't land in a project-readable artifact: the editor keeps its entire override surface, and simply can't show you the text you are replacing. The model string and the canonical settings survive it, because a model id and a temperature are the agent's shape rather than its prose, and an editor that can't see which model an agent runs can't offer to change it.

`'off'` lands in exactly the state a baseline too large to carry lands in: the span is still emitted, `agent_control.baseline` is absent, and `agent_control.baseline_reduction` says `'omitted'`. There's one state on the span for "the document isn't here", rather than a second word to learn.

Leave `report_baseline` unset and the `source` you pass chooses: **`'structure'` for an `'observed'` baseline, `'text'` for a `'code'` one.** An observed baseline is a snapshot of one request, so its text came from whatever that request carried — one tenant's, one user's, one retrieved document's — and reporting it is the case least likely to be what anyone meant. A baseline read off the code is your own words, written to be read.

Whatever the mode, a **dynamic block never contributes its rendered text** and **settings are reduced to the canonical keys**, so one run's data and your `extra_headers` stay out of every report. Those are `build_baseline`'s rules, not this control's.

### What a report carries

One span per agent per process per Logfire project, named `agent_control_config_hint`, with everything a config would be created from on `agent_control.*` attributes: `variable_name` and `agent_name`, `framework` (which Agent Control implementation reported — an adapter passes its framework's slug, and `AgentControl(framework=...)` is where), `baseline_source`, `schema_sha256`, `baseline` and its `baseline_sha256`, `baseline_reduction` and `baseline_bytes`, `resolution_reason`, and `service_name` / `environment` / `service_version` for the deployment that reported it. Each of the last three is left off rather than sent empty.

Nothing on the span says which publication mode produced it, deliberately. A baseline *is* whatever your policy says it is: `baseline_sha256` and `baseline_bytes` describe what was actually reported, so two deployments running the same code under the same policy agree, and nobody reading the span has to reconstruct what a fuller report would have said.

It is a span rather than a log record on purpose: a log below your `min_level` is dropped before it is exported, and getting your agent onto the Agent Control page is not something a logging setting should get a vote on. A baseline over 1 MiB gives up whole sections rather than being cut to length — `tool_definitions` first, then the baseline entirely — because the backend truncates a long attribute in place, and half a JSON document still looks like a string and no longer parses. `baseline_reduction` says which happened, and `baseline_sha256` is taken before any of it, so two reports of one agent agree.

## Writing an adapter

An adapter does five things. Nothing else in `logfire.agent_control` is required, and nothing else is public.

**1. Name the agent's config.** `AgentControl('checkout-assistant', label='production')`. The name you pass is kept verbatim for display and normalized for the variable key; see [Agent name to variable key](#agent-name-to-variable-key).

**2. Report the baseline.** `build_baseline(instructions=..., model=..., settings=..., tools=...)` describes the agent as written, and `control.report_baseline(baseline, resolution)` reports it. **Nothing is written to your project**: the SDK emits one `agent_control_config_hint` span carrying everything a config would be created from, and creating the config — or offering to refresh a stale baseline — happens in Logfire. Hand it the run's own `Resolution` rather than letting it resolve again — a second read could put a version on the span that no request of this run was made under. It reports at most once per process per agent per project, and never raises. Say whether you are describing the agent as written or one request you observed, with `source='code'` or `source='observed'` — it changes what the baseline *means*, and it chooses how much of it leaves your process (see [Publication](#publication)).

**3. Read the published value.** `with control.resolution() as resolution:` resolves once for a run and yields a `Resolution`: `config`, plus the `label`, `version`, and `reason` it came from. Inside that block the resolved label and version ride as OpenTelemetry baggage, so every span and log the run emits says which published version produced it. `control.resolve()` is the one-shot sugar for a framework that has nowhere to hold a context open.

**4. Apply it, in the framework's own per-request hook.**

All three take the config and return a result carrying `.issues`: everything the section could not apply, as `ApplyIssue` records. None of them reports anything itself.

- `apply_instructions(blocks, config)` takes the `Block`s the agent is about to send and returns `.blocks`, with published text swapped in, removed, or added.
- `apply_tool_definitions(tools, config)` takes the `ToolDef`s the agent is about to advertise and returns `.tools` with managed names and descriptions applied, `.routes` mapping advertised name back to code name, and `.forward` and `.reverse` for a framework where a bare name is not an identity. Pass `reserved={...}` to keep names the adapter needs for itself out of reach of a rename.
- `apply_settings(config, support=...)` returns `.settings`, the patch to merge over the agent's own. `merge_settings(code, published, run_explicit)` is that merge, in the contract's order; `canonical_settings(settings)` is the reverse, for a baseline.

**5. Declare what you can apply, and report the rest.** `AgentSupport` is your adapter's own capability, declared once: the `sections` it can apply, the canonical `settings` it can lower, its named instruction `destinations`, how faithfully it can tell a per-run setting from a default (`precedence`), and what one resolved config covers (`resolution_unit`). Pass it to `apply_settings` and a published section or setting you cannot act on is reported rather than silently doing nothing. The Logfire UI reads the same declaration to grey out what would be pointless to publish.

Then hand every section's issues to `control.report(*issues)` **once** (or, for an adapter whose framework has its own notion of a managed capability and so never holds an `AgentControl`, `report_issues(policy, issues)`), which applies `on_unmatched`: `'warn'` (the default, once per process per message), `'error'`, or `'ignore'`. Reporting after everything is planned is why the helpers do not report for you -- `'error'` raises one `UnmatchedConfigError` naming every issue, instead of failing on whichever section you happened to apply first. An instruction `id` no block carries, a tool override no tool matches, a rename that collides, a settings key your framework can't lower, a whole section it cannot reach: each is a place where Logfire shows one thing and the agent does another, and the adapter is the only thing that can see it.

A published setting your adapter *can* lower goes to the provider, and providers refuse settings -- a `presence_penalty` some models answer with a `400`, a `temperature` alongside a reasoning effort. Which settings a given model accepts is deliberately not in this contract: `AgentSupport` says what the adapter can do, not what a model will take, so keeping a setting away from a model that refuses it is your adapter's own reasoning to do.

Here is an adapter end to end, for an imaginary framework whose agent has one prompt string, a list of tools, a hook around each run, and a hook before each model request:

```python skip="true"
from logfire.agent_control import (
    AgentControl,
    AgentSupport,
    Block,
    ToolDef,
    apply_instructions,
    apply_settings,
    apply_tool_definitions,
    build_baseline,
    canonical_settings,
    merge_settings,
)

# What this adapter can do with a published value, declared once rather than inferred.
SUPPORT = AgentSupport(
    sections=frozenset({'instructions', 'model', 'settings', 'tool_definitions'}),
    settings=frozenset({'max_tokens', 'temperature', 'top_p', 'stop_sequences'}),
    precedence='exact',  # This framework's hook says which settings the call itself passed.
    resolution_unit='run',
)


def agent_control(agent, name, *, label=None):
    """Make `agent` configurable from Logfire, and return it."""
    control = AgentControl(name, label=label)

    def around_run(run):
        # One resolution per run, held for the whole of it: every span inside carries the label and
        # version that produced it, and a value published mid-run applies to the next one. It also
        # makes `control.current_resolution()` answer with this one resolution for the whole run,
        # which is how the per-request hook below reads it without resolving again.
        with control.resolution():
            return run()

    def before_request(request):
        # This framework's agent declares a prompt template and interpolates it per request, so the
        # adapter can address the two halves separately: the template is the block someone edits
        # from Logfire, and what this request interpolated into it is not.
        blocks = [
            Block(agent.prompt_template, id='agent'),
            Block(request.interpolated, id='agent:context', dynamic=True),
        ]
        tools = [ToolDef(t.name, t.description, t.parameters_json_schema) for t in request.tools]
        resolution = control.current_resolution()
        control.report_baseline(
            # The dynamic block goes in carrying its id and no text: the baseline is reported where
            # every project member can read it, and its text is one request's. `build_baseline` drops
            # the text for it. Reporting the *static* block is what lets the editor offer the prompt
            # for editing at all -- so an adapter whose framework hands it only a finished string,
            # with no seam between the two, marks the whole thing dynamic and offers no prompt
            # editing rather than reporting one request's rendering as if it were the code.
            build_baseline(
                instructions=blocks,
                model=agent.model,
                settings=canonical_settings(agent.settings),
                tools=tools,
            ),
            resolution,
            # This framework's tool list is only knowable once a request is assembled, so what is
            # reported describes *this* request rather than the code. That also makes the default
            # publication `'structure'`: every seam, and none of this request's text.
            source='observed',
        )

        config = resolution.config
        if config is None:
            return request  # Nothing published: the agent runs exactly as written.

        # Each helper plans its section and hands back what it could not apply. Nothing is reported
        # until every section has been planned, which is what lets `on_unmatched='error'` fail once
        # naming all of it rather than on whichever section ran first.
        instructions = apply_instructions(blocks, config)
        # The same blocks the baseline described, so what the editor offered is what gets applied.
        request.prompt = '\n\n'.join(block.text for block in instructions.blocks)
        applied = apply_tool_definitions(tools, config, reserved=request.provider_tool_names)
        by_name = {tool.name: tool for tool in request.tools}
        request.tools = [by_name[applied.routes[t.name]].with_definition(t) for t in applied.tools]
        request.routes = applied.routes  # The dispatcher maps a name the model called back with this.
        settings = apply_settings(config, support=SUPPORT)
        # Published settings beat the agent's own; the ones this call passed explicitly beat both.
        merged = merge_settings(agent.settings, settings.settings, request.explicit_settings)
        request.settings = merged.settings
        if config.model is not None:
            request.model = config.model
        control.report(*instructions.issues, *applied.issues, *settings.issues)
        return request

    agent.around_run(around_run)
    agent.before_request(before_request)
    return agent
```

Two things every adapter has to decide for its framework, because frameworks genuinely differ.

The first is what a rename means on the way back in: whether a renamed tool reaches your implementation under its old name or its new one, and whether history the model already saw needs remapping too. `routes` is the mapping for that, and it is flat — advertised name to code name — so it is exact only under the default `collision_scope='global'`, where an advertised name identifies a tool by itself. An adapter that passes `collision_scope='toolset'` has said that two toolsets may advertise the same name, so it dispatches through `reverse`, keyed on `(toolset, advertised name)`, and rewrites outgoing names through `forward`. Reaching for `routes` there would send a call to whichever of the two got there first.

The second is how the canonical `provider:model` string maps to the framework's own model convention. Pass a string with no `:` through untouched, so a framework-native id keeps working.

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

A baseline is a *description of the agent*, reported to Logfire and rendered by the editor as the thing a managed value is layered onto. It is never resolved and never applied. Because it is read by every member of the project and treated as the truth about the code, it owes the editor exactly these things:

- **Stable ids.** Every block the editor may offer an override for carries the `id` that addresses it, and that id is stable across requests and deploys. A positional id that moves when someone reorders their prompt sources is not stable.
- **A dynamic block carries `{id, dynamic: true}` and never text.** Its text is one request's rendering of whatever that run carried (a tenant name, a user id, a retrieved document), so publishing it leaks one run's data into a shared variable and invites an override that pins it forever. A dynamic block with nothing to key it on is left out entirely, since the editor could neither show nor address it.
- **Every top-level parameter of every tool is listed**, with `description` when the code has one and an empty entry when it does not.
- **Settings are canonical keys with validated values.** Everything else, including provider-specific keys, `extra_headers`, and `extra_body`, stays in code, because that is where authorization headers and signed bodies live. `canonical_settings` is that filter.
- **`toolset` is present when known and absent when not.** Never guessed: an override narrowed to a toolset only works if the value the editor shows is the value the override can be written against.
- **Unrepresentable values are omitted and reported, never approximated.** A reasoning effort a framework spells `'max'` is not `'xhigh'`, and a timeout outside the representable range is not the nearest one that fits.
- **A code baseline is not a first-request observation**, and the adapter says which it is reporting with `report_baseline(..., source='code' | 'observed')`.

### Parsing a published value

Leniency is **per section**: a section, entry, or setting this release can't make sense of costs only itself, and everything around it still applies. A value that fails validation outright falls back through Logfire's resolution to the code-defined agent *in its entirety*, which is what makes that rule load-bearing rather than polite. Four consequences worth stating, because they are where two independent implementations drift:

- **An invalid `model` drops only `model`.** The section is the unit because `model` has no entries to degrade one at a time.
- **The instruction budget is charged to surviving entries only.** An entry dropped for being malformed adds nothing to the request, so charging it would let one bad entry shrink the budget for the good ones.
- **Text length is counted in Unicode code points**, so an emoji costs the same in every SDK.
- **`''` is never a value.** Not "no model", not "no instructions", not "no name": it is a field someone left half-filled, and `null` already means "leave this to code".

Values are read **strictly** with respect to JSON types: `1` is a valid `temperature` because JSON writes `1` for `1.0`, while `"0.4"` is a string where the stored schema says `number`, and is dropped. Code-side values going into a baseline are read leniently instead, because they come from a framework's own objects rather than from the wire.

## What it guarantees

**Nothing published can crash the SDK.** An unreachable Logfire, a missing value, or one this release can't parse leaves `resolve()` returning `None`. Beyond that, a value the contract can't act on costs only the piece containing it (one setting, one tool override, one block) and is reported once per process, so one unfamiliar key from a newer UI never silently un-manages the rest.

That is not a promise about the request. A **setting** is forwarded to the provider, and providers refuse settings: some models answer a `presence_penalty` with a `400`, and some refuse a `temperature` sent alongside a reasoning effort. Which settings a model accepts is not part of this contract and is not something the Logfire UI can warn you about, so editing settings in Logfire can take a live agent down the same way editing them in code can. Keeping a published setting away from a model that would refuse it is the adapter's own job.

**Overrides never move the prompt-cache boundary.** A replaced block keeps its position and its static/dynamic side, and an added block lands at the end of the leading run of static blocks, so published text stays inside the prefix a provider can cache.

**Only what the model is told about a tool is editable.** A rename that collides with another advertised name, or with a name the adapter reserved for a handoff or a provider tool, is dropped under `on_unmatched` while that override's other patches still apply, so every tool keeps a name the model can call.

**The SDK never writes a managed variable.** Reporting a baseline emits a span; creating the config, and offering to refresh a stale baseline, happen in Logfire. So an Agent Control deployment needs only a span-write token, and no publish can carry away a value, a label, or a rollout somebody saved in the UI — the failure mode a client-side refresh of a variable's `example` has and cannot be made not to have, because `update_variable` PUTs the whole definition and takes no `If-Match`. It also means your agent's config does not exist until somebody creates it in Logfire, which is one click on the baseline your agent just reported.

**Every agent reports, whether or not it has a config.** An agent that reported only while unconfigured would go quiet the moment somebody configured it, and the baseline stored against it would describe the deployment it was created from forever. So the report says what the code says *now*, and carries `agent_control.resolution_reason` to say which job it is for: `code_default` is a baseline waiting for a config to be created from it, `resolved` is one that may only be refreshing a stale example. What it carries is always the code and never the managed value — that is what makes a diff a diff.

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
