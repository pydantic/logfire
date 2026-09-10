# Agent Control for LiveKit Agents

[Agent Control](agent-control.md) for [LiveKit Agents](https://docs.livekit.io/agents/). Decorate an agent class once, and its instructions, its model, its model settings, and the descriptions its tools show the model become editable from the Logfire UI — versioned, labelled, rolled out to a percentage of traffic, and rolled back as one unit, without a redeploy. Everything you do not change in Logfire keeps doing what your code says, and removing a change there puts that piece back.

You need `livekit-agents`, a Logfire project, and `logfire.configure()` with a token that can read the project's variables — and write them, unless you turn baseline publishing off.

!!! note "Install the agent-control-livekit extra"
    ```bash
    pip install 'logfire[agent-control-livekit]'
    ```

## Quick start

```python skip-run="true"
from livekit.agents import (
    Agent,
    AgentSession,
    JobContext,
    RunContext,
    WorkerOptions,
    cli,
    function_tool,
)
from livekit.plugins import openai

import logfire
from logfire.agent_control.livekit import agent_control

logfire.configure()


@function_tool
async def get_weather(ctx: RunContext, city: str) -> str:
    """Get the current weather for a city.

    Args:
        city: The city to look up.
    """
    return f'sunny in {city}'


@agent_control(name='checkout_assistant', label='production')
class CheckoutAgent(Agent):
    def __init__(self) -> None:
        super().__init__(
            instructions='You are a concise checkout assistant.',
            tools=[get_weather],
            llm=openai.LLM(model='gpt-5.2'),
        )


async def entrypoint(ctx: JobContext) -> None:
    session = AgentSession()
    await session.start(agent=CheckoutAgent(), room=ctx.room)


if __name__ == '__main__':
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint))
```

## `agent_control`

```python skip="true"
agent_control(
    agent_cls=None,
    *,
    name,
    label=None,
    on_unmatched='warn',
    publish_baseline=True,
    logfire_instance=None,
)
```

It **returns a subclass** of the class you gave it, and never modifies that one: the class you wrote keeps running on its code, and can be bound again for another label. Use it as a decorator, as above, or call it directly — `agent_control(CheckoutAgent, name='checkout_assistant')` — when the class is defined elsewhere. The subclass keeps the original's `__name__`, `__qualname__`, `__module__` and docstring, and therefore its LiveKit `id`, which every span it emits is labelled with. It overrides `__init__`, `on_enter` and `llm_node`, and each one calls into yours.

| Option | What it does |
|---|---|
| `agent_cls` | The agent class to manage. Leave it out to use `agent_control` as a decorator. |
| `name` | **Required.** The name the config is keyed on, as `agent__<name>`. Explicit because LiveKit's own `Agent(id=...)` is ignored on the base `Agent` class — every one of them reports `default_agent` — so a name taken from the agent would point half the agents in a worker at one config. |
| `label` | The label to resolve, such as `'production'`. `None` lets the variable's own targeting rules and rollout choose. |
| `on_unmatched` | What to do about a published entry that reaches nothing here. `'warn'` (the default) says so once per process, `'error'` fails the request, `'ignore'` says nothing. |
| `publish_baseline` | Whether to publish the code baseline the editor diffs against. Turn it off when the variables token is intentionally read-only. |
| `logfire_instance` | The Logfire instance to resolve and publish through. Defaults to the global one. |

While something is published, the agent's `llm` is a thin request boundary in front of the model it actually runs on: it reports that model's `model` and `provider`, forwards its metrics and its errors, and applies the published config to the call your `llm_node` makes — so your node keeps running and keeps deciding what to send. It is removed again the moment nothing is published.

A handoff moves the conversation to a *different* `Agent` class, and that class is what a config is about. Decorate each one you want managed, under a name of its own.

### Named prompt blocks

LiveKit gives an agent one prompt, so out of the box a published value can replace it whole or add to it. To make parts of it separately editable, assemble it with `instruction_blocks`:

```python
from livekit.agents import Agent

from logfire.agent_control.livekit import agent_control, instruction_blocks


@agent_control(name='checkout_assistant', label='production')
class CheckoutAgent(Agent):
    def __init__(self) -> None:
        super().__init__(
            instructions=instruction_blocks(
                {
                    'agent': 'You are a concise checkout assistant.',
                    'refunds': 'Always confirm the order total before refunding.',
                },
                audio='Keep spoken answers to one sentence.',
            )
        )
```

Each key is a block someone can rewrite or remove in Logfire on its own, and the blocks are joined the way LiveKit joins prompt parts, so the agent sends exactly the prompt it would have sent as one string. The result is an `Instructions`, so `audio=` and `text=` are LiveKit's own modality variants and keep working as they do — they are addressed as `agent:audio` and `agent:text`, and a block may not claim either of those ids for itself.

## What becomes editable

Two paths, because LiveKit has two. A **stateless** `llm.LLM` is configured per model request, in `Agent.llm_node`. A **realtime** `llm.RealtimeModel` never reaches `llm_node` at all: it is configured once per session, over the session update that `Agent.update_instructions` and `Agent.update_tools` send, and only for what the plugin says can be changed mid-session.

### Instructions

| Source | Block ID or runtime mapping | Support | Conditions and unmatched behaviour |
|---|---|---|---|
| `Agent(instructions='...')` | block `agent` | Yes | Replace its text, remove it, or add a block after it. |
| `instruction_blocks({...})` | one block per key | Yes | Each block is editable on its own. |
| `instruction_blocks(..., audio=...)`, `Instructions(audio=...)` | block `agent:audio` | Conditional | Stateless: reachable only on a turn that is actually sending the audio variant; a value for the other variant is reported on that turn. Realtime: the session renders one variant for its whole life — audio when the model has audio output, text otherwise — and only that one is reachable. |
| `instruction_blocks(..., text=...)`, `Instructions(text=...)` | block `agent:text` | Conditional | As `agent:audio`. |
| `agent.update_instructions('...')` at runtime | block `agent` | Yes | It replaces the whole prompt with a plain string, so from that point the agent has one block keyed `agent` and the blocks you declared reach nothing and are reported. |
| Instructions that vary per request | — | No | LiveKit has no per-request instruction callable; the seam above is the only one there is. |

### Model

| Source | Block ID or runtime mapping | Support | Conditions and unmatched behaviour |
|---|---|---|---|
| `Agent(llm=...)` or `AgentSession(llm=...)`, a stateless `llm.LLM` | `provider:model` | Yes | `openai:gpt-5.2`, `anthropic:claude-fable-5-1`, `google:gemini-3-flash`. Built with the plugin you already use where the provider matches — same class, same client, so the base URL, credentials and HTTP client come along and only the model name changes. Otherwise that provider's plugin, then LiveKit Inference; a string with no `:` goes to LiveKit Inference untouched (`openai/gpt-4.1`). A name this process cannot build is reported and the agent keeps its own model. |
| A `llm.RealtimeModel` | — | No | A running realtime session cannot be moved to another model. Reported. |

The provider ids are Pydantic AI's, which is the canonical form the config contract uses: `google` is the Gemini API and `google-cloud` is Vertex. The LiveKit google plugin speaks both from one class, and which one an agent is on is read off the `genai` client it built, so a Vertex agent is published as `google-cloud:` and comes back as one. `google-gla` and `google-vertex`, which Pydantic AI v1 used for the same two, are still accepted so that a config published against a v1-era agent keeps applying; nothing published from here emits them.

### Model settings

Every canonical setting is sent through `LLM.chat()`, so what a plugin can be told is what its `chat()` spreads into the provider request. A setting a plugin has no name for is reported and left code-defined. **None of these reach a realtime model** — they take a response length, a voice and turn-detection options rather than sampling settings — so on that path every one of them is reported and not applied.

| Canonical field | Runtime mapping | Support | Conditions and unmatched behaviour |
|---|---|---|---|
| `temperature` | `extra_kwargs['temperature']` | Conditional | OpenAI, LiveKit Inference, Anthropic and Google. Reported on a plugin outside that table. |
| `top_p` | `extra_kwargs['top_p']` | Conditional | As `temperature`. |
| `max_tokens` | `max_completion_tokens` (OpenAI, Inference), `max_output_tokens` (Google) | Conditional | **Not on Anthropic**, whose plugin writes its own `max_tokens` into every request and would overwrite a published value rather than merely losing to an explicit one. Reported there. |
| `top_k` | `extra_kwargs['top_k']` | Conditional | **Anthropic and Google only.** OpenAI has no such parameter. |
| `seed` | `extra_kwargs['seed']` | Conditional | OpenAI, LiveKit Inference and Google. |
| `presence_penalty` | `extra_kwargs['presence_penalty']` | Conditional | **OpenAI and LiveKit Inference only.** The Google plugin forwards it and the Gemini API answers `400 Penalty is not enabled for models/<model>`, so it is reported there rather than sent. |
| `frequency_penalty` | `extra_kwargs['frequency_penalty']` | Conditional | As `presence_penalty`. |
| `stop_sequences` | `stop` (OpenAI, Inference), `stop_sequences` (Anthropic, Google) | Conditional | Reported on a plugin outside that table. |
| `parallel_tool_calls` | `LLM.chat(parallel_tool_calls=...)` | Conditional | Part of `chat()` itself, so every plugin takes it — except Google's, which accepts it and maps it nowhere. Reported there. |
| `timeout` | narrows this request's `APIConnectOptions` | Yes | Part of `chat()` itself. |
| `thinking` | `extra_kwargs['reasoning_effort']` | Conditional | **LiveKit Inference only**, and only as an effort level; `true`/`false` names no level and is reported. Not on the OpenAI plugin, which writes `reasoning_effort` itself for every model that takes one — so a published value always loses that collision — while OpenAI refuses the argument outright on every model that does not. Not on Anthropic or Google either, whose plugins want a token budget the contract does not carry, and where sending the wrong shape *fails the request*. |

A plugin this package has no table for — a community plugin, a `FallbackAdapter`, a test double — gets only what `LLM.chat` itself defines: `parallel_tool_calls` and `timeout`. Every provider-native name would be a guess, and the rest are reported.

**A setting you also pass to the plugin constructor wins over the published one.** Every LiveKit plugin merges its constructor options *over* the per-request ones, which is backwards from what Agent Control wants and cannot be changed from outside the plugin. It is reported when it happens, naming the setting. Leave a setting off the constructor to manage it from Logfire.

### Tools

| Source | Block ID or runtime mapping | Support | Conditions and unmatched behaviour |
|---|---|---|---|
| A `@function_tool`'s name, description and parameter descriptions | the tool's own name | Yes | Parameter names, types, requiredness, validation and the implementation stay code-defined. |
| A `@function_tool(raw_schema=...)`'s name, description and parameter descriptions | the tool's own name | Yes | Its schema is carried whole, so it is patched in place. |
| A tool inside an `llm.Toolset` (including an MCP server's) | grouped under the toolset's `id` | Conditional | Stateless: editable, and an override can be narrowed to one group with `toolset`. Realtime: the session's tools are replaced in place and rebuilding a `Toolset` is not this package's to do, so an override aimed at one reaches nothing and is reported. |
| A tool an `AgentSession(tools=...)` contributes | the tool's own name, grouped as above | Conditional | Stateless: editable like any other. Realtime: only the agent's own tools are replaced, so an override for a session tool is reported. |
| An `llm.ProviderTool` — web search, code execution | — | No | It is advertised as configuration under its own `id`, with no description or schema of ours to patch. Not listed in the baseline, and an override naming one is reported. Its id is also *reserved*: a rename onto it is refused and reported, while that override's other patches still apply. |
| Which tools exist, their parameters, their types, what they do | — | No | Those are your code. Agent Control edits what the model is told. |

A rename that collides with another advertised name is dropped and reported, and the tool keeps its code-side name, so every tool always has a name the model can call.

## Resolution, baseline and precedence

**The unit of resolution is one model request.** LiveKit's only hook around a stateless model call is `Agent.llm_node`, which is per request, so the config is read there and held open for the whole request: the prompt, the tools, the settings and the model of one request always come from one published version, and every span inside it — the model request, each tool call — carries the label and version that produced it. A turn that makes two model requests can legitimately resolve twice, so a value published between them takes effect on the second. On the realtime path the unit is the session: the config is read once in `on_enter`, and again whenever the agent is entered.

**The baseline is published once per process**, from the first model request (or the first `on_enter` on the realtime path) — the first moment the model the agent runs on and the tools the session contributes are knowable. It describes the agent *as written*: the prompt the class was constructed with, its model, the settings that plugin would actually send, and its tools' definitions. A prompt replaced at runtime by `update_instructions()` is one run's decision and is never published as the code's. On the realtime path it lists only the tools that path can actually edit.

**Precedence is code, then published, then the values a request set explicitly.** The default node passes no settings at all, so on the usual path the published settings are what the request goes out with. A custom `llm_node` that passes `extra_kwargs`, `parallel_tool_calls` or a `tool_choice` has computed those for this one request, and they win over the published ones — the connection options it forwards are the session's own configuration, so a published `timeout` still narrows them. A `session.generate_reply(instructions=...)` is appended after the managed prompt, as LiveKit appends it after the agent's own.

**Publishing only a `model` keeps the settings your code chose.** The replacement is a fresh plugin instance carrying its class's defaults, so the temperature and token budget you set on the model you replaced are carried across as request settings — underneath the published `settings` section. One the new plugin family has no name for cannot move, and is reported.

## How a renamed tool looks from your code

**On the stateless path your code still sees the old name.** Rename `get_weather` to `lookup_weather` in Logfire and the model is offered `lookup_weather`, is told to use it by a `tool_choice` that forced `get_weather`, calls it by that name, and sees its own earlier calls under that name in the conversation. The call is mapped back before LiveKit routes it, so your function runs unchanged, `ctx.function_call.name` is still the name you wrote, and the history the agent keeps reads that way too.

**On the realtime path it does not, and cannot.** A realtime session's tool list *is* its dispatcher: the tools that go out over the session update are the ones a call is looked up in, and there is no seam between the model's answer and that lookup to map a name back through. Your tool still runs, with its arguments validated and its `RunContext` injected exactly as before — but `ctx.function_call.name`, name-keyed hooks, and the session history all say `lookup_weather`. Every realtime rename is reported through `on_unmatched` for that reason.

## Known limits

- **Realtime models are configured per session, not per request.** Instructions and tool definitions are sent when the agent is entered, and only if the plugin reports that they can be changed at all; a model, any model setting, and any override aimed at a `Toolset`'s tools are reported rather than half-applied. See the tables above for each.
- **Editing a parameter description changes how that one tool is sent.** A `@function_tool`'s schema is derived from its signature, so a patched description has to go out as a raw JSON Schema — which turns off the provider's strict function-calling mode for that tool. Renaming a tool or rewording its description does not do this. What the tool *does* is unchanged either way: the raw clone is a bridge back to the original, which still validates the model's arguments and injects the `RunContext` before your function runs.
- **`agent.update_instructions()` drops the block structure.** It replaces the whole prompt at runtime, so from that point the agent has one block keyed `agent` and the blocks you declared apply to nothing (and are reported as such). On the realtime path a prompt you replace that way becomes the code side: withdrawing a published override puts *yours* back, not the one the class was constructed with.
- **One config per agent class, not per session.** `agent_control` is called once, where the class is defined, and every instance of that class shares it.
- **Publishing an edit changes the cached prefix once**, the same as a redeploy would. Blocks are never reordered, and an added block lands after your last static block, so it stays inside the prefix a provider can cache.
- **A published value that reaches nothing costs only the piece containing it.** An unreachable Logfire, a missing value, or one this release cannot parse means the agent runs exactly as written — including your own `llm_node`; beyond that, an entry that matches nothing warns once per process, and `on_unmatched='error'` fails the request instead while `'ignore'` says nothing. What is *not* covered by that: a published block or tool description is model input like any other, so text published into one can change what the agent does, and `on_unmatched='error'` deliberately turns an unmatched entry into a failed request.
- **Publishing the baseline can lose a concurrent UI publish.** The variable is created rather than overwritten when it is missing, and re-read immediately before the write, but a value saved in the UI inside that round trip is overwritten by the older state. Set `publish_baseline=False` and create the variable in the UI where that window is not acceptable.
- **`livekit-plugins-anthropic` 1.8 does not work with the `anthropic` SDK from 1.0.** The plugin hands its `anthropic.AsyncClient` an `httpx.AsyncClient` where the SDK now requires an `httpx2.AsyncClient`, so constructing `anthropic.LLM(...)` raises `TypeError` — and the same rewrite moved `temperature`, `top_p` and `top_k` off `messages.create()`, so the plugin's own values for them raise too. Only `stop_sequences` is reachable on that pairing. This is between those two packages and not something Agent Control can bridge; pin `anthropic<1` until the plugin catches up, in which case the whole Anthropic row above applies.

## Next steps

- [Agent Control](agent-control.md): the config contract every adapter shares, what it guarantees, and how to write one for another framework.
- [Managed Variables](managed-variables/index.md): the versions, labels, rollouts, and targeting that Agent Control is built on.
