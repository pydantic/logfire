# Agent Control for the OpenAI Agents SDK

[Agent Control](index.md) for the [OpenAI Agents SDK](https://openai.github.io/openai-agents-python/). Wrap an agent once, and its instructions, its model, its model settings, and the descriptions its tools show the model become editable from the Logfire UI: versioned, labelled, rolled out to a percentage of traffic, and rolled back as one unit, without a redeploy. Everything you do not change in Logfire keeps doing what your code says, and removing a change there puts that piece back.

You need a Logfire project and `logfire.configure()` with a token that can read the project's variables — and write them, unless you turn baseline publishing off.

!!! note "Install the agent-control-openai-agents extra"
    ```bash
    pip install 'logfire[agent-control-openai-agents]'
    ```

    It pulls in the [Agent Control core](index.md) and `openai-agents`.

## Quickstart

```python skip-run="true" skip-reason="makes a real model request"
import asyncio

from agents import Agent, Runner, function_tool

import logfire
from logfire.agent_control.openai_agents import agent_control

logfire.configure()


@function_tool
def get_weather(city: str) -> str:
    """Get the current weather for a city.

    Args:
        city: City to look up.
    """
    return f'sunny in {city}'


agent = agent_control(
    Agent(
        name='checkout_assistant',
        instructions='You are a concise checkout assistant.',
        tools=[get_weather],
        model='gpt-5.6-luna',
    ),
    label='production',
)

result = asyncio.run(Runner.run(agent, 'Refund my last order.'))
print(result.final_output)
```

## `agent_control`

```python skip="true"
agent_control(
    agent,
    *,
    name=None,
    label=None,
    on_unmatched='warn',
    publish_baseline=True,
    logfire_instance=None,
    instructions=None,
    provider=None,
)
```

It **returns a copy** of the agent you passed, and never modifies that one: it keeps running on its code, and can be wrapped again for another label. The copy is an `Agent` in every respect, of a one-off subclass of the class you passed — the SDK's per-turn `get_all_tools` is where the config is resolved for the whole run, which is what lets the prompt and the model request of one turn apply the same published version. Clone it, hand it to `Runner`, use it as a handoff or an `Agent.as_tool`: it behaves like the agent it came from.

| Option | What it does |
|---|---|
| `name` | The name the config is keyed on, as `agent__<name>`. Defaults to `agent.name`, which the SDK already requires and already puts on this agent's spans, so the config and those spans agree by construction. |
| `label` | The label to resolve, such as `'production'`. `None` lets the variable's own targeting rules and rollout choose. |
| `on_unmatched` | What to do about a published entry that reaches nothing here. `'warn'` (the default) says so once per process, `'error'` fails the request, `'ignore'` says nothing. |
| `publish_baseline` | Whether to publish the code baseline the editor diffs against, on the first model request. Turn it off when the variables token is intentionally read-only. |
| `logfire_instance` | The Logfire instance to resolve and publish through. Defaults to the global one. |
| `instructions` | The prompt as named blocks; see below. |
| `provider` | The `ModelProvider` that resolves model names, defaulting to `MultiProvider()` — the SDK's own default. |

Each agent in a handoff chain is its own config, and has to be wrapped in its own right.

### Named prompt blocks

The SDK has one prompt, so out of the box a published value can replace it whole or add to it. To make parts of it separately editable, hand the parts to `agent_control` instead of to the agent:

```python skip="true"
from datetime import date

from agents import Agent

from logfire.agent_control.openai_agents import agent_control

agent = agent_control(
    Agent(name='checkout_assistant', tools=[get_weather], model='gpt-5.6-luna'),
    instructions={
        'agent': 'You are a concise checkout assistant.',
        'refunds': 'Always confirm the order total before refunding.',
        'today': lambda ctx, agent: f'Today is {date.today()}.',
    },
    label='production',
)
```

Each key is a block someone can rewrite or remove in Logfire on its own. Fixed blocks are sent first, in the order you declare them, then the computed ones — so a block that changes per request never moves the cacheable prefix. The mapping is the whole prompt: leave `Agent(instructions=...)` unset.

## What becomes editable

| Source / canonical field | Block ID or runtime mapping | Support | Conditions and unmatched behaviour |
|---|---|---|---|
| `Agent(instructions='...')` | block `agent` | Yes | Replace its text, remove it, or add a block after it. |
| Instructions written as a function | block `agent`, dynamic | Add only | Its text is recomputed per request, so a published value would pin one rendering. A value addressing it is reported and not applied; new blocks can still be added around it. |
| `agent_control(instructions={...})` | one block per key | Yes | Fixed blocks are editable; a block written as a callable is add-only, as above. |
| An agent with no prompt at all | block `agent` | Add only | A published block reaches an agent that has no `instructions`. |
| `Agent(prompt=...)`, a prompt stored in the OpenAI dashboard | — | No | Its text lives on OpenAI's side and never reaches the SDK, so there is nothing here to edit or to report against. |
| Model | `provider:model` | Yes | `openai:gpt-5.6-luna` is a bare SDK name; every other provider is routed through `litellm/`, so that extra has to be installed. A handful of provider ids are spelled differently by the gateway and are translated; see [Provider ids](#provider-ids). A string with no `:` is handed to your provider as written. A name this process cannot build is reported and the agent keeps its own model. |
| `max_tokens` | `ModelSettings.max_tokens` | Yes | |
| `temperature` | `ModelSettings.temperature` | Yes | Sent, and taken by OpenAI — but its own reasoning models refuse a request that carries it *and* asks the model to reason; see [What the provider does with a setting](#what-the-provider-does-with-a-setting). |
| `top_p` | `ModelSettings.top_p` | Yes | As `temperature`. |
| `parallel_tool_calls` | `ModelSettings.parallel_tool_calls` | Yes | Left out of a request that advertises no tools. |
| `thinking` | `ModelSettings.reasoning.effort` | Yes | `false` means effort `none`, `true` means `medium`, and `minimal`/`low`/`medium`/`high`/`xhigh` mean themselves. `summary` and `context`, which nobody published, are kept. |
| `presence_penalty` | `ModelSettings.presence_penalty` | Conditional | Sent by the Chat Completions and LiteLLM models. The Responses API has no request field for it, so on a Responses model it is reported and not applied — and left out of the baseline. |
| `frequency_penalty` | `ModelSettings.frequency_penalty` | Conditional | As `presence_penalty`. |
| `top_k` | — | No | `ModelSettings` has no field for it, and an `extra_args` key the Responses API has no parameter for is not sent and ignored: it raises a `TypeError` out of the OpenAI client's own signature, before a request is built. Reported. |
| `seed` | — | No | As `top_k`. Reported. |
| `stop_sequences` | — | No | As `top_k`. Reported. |
| `timeout` | — | No | `ModelSettings` carried no such field before `openai-agents` 0.22, and where it does, the runner reads it off the settings *before* a model wrapper is handed them — so a value applied here would be shown as applied and never be. Reported. |
| A function tool's name, description, and parameter descriptions | the tool's own name, grouped by toolset | Yes | Parameter names, types, requiredness, and the implementation stay code-defined. A rename onto a name another tool, a handoff, or a hosted tool already answers to is refused and reported, while that override's other patches still apply. |
| Hosted tools — web search, file search, hosted MCP, computer use, code interpreter | — | No | The SDK sends them as configuration and shows the model no description or schema of its own, so there is nothing to patch. They are not listed in the baseline, and an override naming one is reported as matching no tool. |

Tools an MCP server contributed are editable like any other and are grouped in the editor under `mcp:<server name>`; an agent exposed with `Agent.as_tool` is grouped under `agent:<agent name>`, and everything else under `<agent>`.

### Provider ids

The contract's model string is `provider:model`, and the SDK's `MultiProvider` routes on `prefix/model`, where a bare name is OpenAI's and `litellm/` reaches everything else. `openai:gpt-5.6-luna` therefore becomes `gpt-5.6-luna`, and every other provider becomes `litellm/<provider>/<model>`.

Most provider ids are spelled the same on both sides. These are the ones that are not, and are translated:

| Contract | Gateway |
|---|---|
| `google` | `gemini` |
| `google-cloud` | `vertex_ai` |
| `fireworks` | `fireworks_ai` |
| `together` | `together_ai` |
| `moonshotai` | `moonshot` |
| `bedrock-mantle` | `bedrock_mantle` |
| `vercel` | `vercel_ai_gateway` |

`google-gla` and `google-vertex`, which is how the two Google providers were spelled before Pydantic AI v2, are still *read* — a config published against an agent from that era keeps working — and never written back: a baseline always says `google` or `google-cloud`.

A provider id with no entry goes to the gateway as written rather than guessed at, which is also how a framework-native id someone typed into Logfire keeps working.

### What the provider does with a setting

A setting this adapter can lower is one it puts in the request. What the provider then does with it is the provider's, and two of the rows above are worth knowing about because the answer is not "applies it":

- **OpenAI's reasoning models refuse `temperature` and `top_p` once the same request asks them to reason.** Sent on their own — or alongside `thinking: false`, which is effort `none` — both are accepted. Sent alongside any other `thinking` value, a GPT-5-class model answers `400 Unsupported parameter: 'temperature' is not supported with this model`, and the request fails rather than the setting being ignored. So publishing a sampling setting and a thinking level together for one of those models breaks every request that agent makes. Nothing in `ModelSettings`, in the SDK, or in the contract says which efforts a given model will take a sampling setting with, so the adapter sends what you published rather than dropping it on a guess.
- **A Responses request never carries `presence_penalty` or `frequency_penalty`.** The fields exist on `ModelSettings` because the Chat Completions and LiteLLM models send them; the Responses model has no request parameter for either, so on a Responses model a published value for one is reported and not applied, and neither is offered in the baseline.

## How a renamed tool looks from your code

Rename `get_weather` to `lookup_weather` in Logfire and the model is offered `lookup_weather`, is told to use it by a `tool_choice` that forced `get_weather`, calls it by that name, and sees its own earlier calls under that name in the conversation. **Your code still sees `get_weather`**: the call is routed back to the tool you wrote, under the name you wrote, before the runner ever looks at it. Nothing in your function, your schema, your run items, or your logs changes.

The exception is history the *provider* keeps: with `previous_response_id` or `conversation_id`, the turns before this one live on OpenAI's side, where nothing this adapter does can reach them. A rename published mid-conversation is visible to the model there under whichever name each turn was recorded with.

## Resolution, baseline and precedence

**The unit of resolution is one run.** The config is read once, at the top of the run's first turn, and every turn of that run applies that one value: the prompt, the tools, the settings and the model of a turn can never come from two different published versions, and a value published mid-run takes effect on the next run rather than between two turns of this one. The prompt is assembled and the model request is made inside that resolution's telemetry, so the generation span Logfire records the request from carries the label and the version that produced it.

**The baseline is published once per process**, on the first model request — which is the first moment the agent's whole tool list is knowable, since that is when a tool gated on `is_enabled` is admitted and a tool an MCP server contributed arrives. It describes the agent *as written*: your declared blocks, your model, the settings that model would actually send, and your tools' definitions. A block written as a function contributes that it exists and never its text, since that text is one request's rendering and the baseline is readable by everyone in the project.

**Precedence is per-run, then published, then code.** A `RunConfig(model_settings=...)` you pass to one run beats the published settings for the keys it sets, and the published settings beat the agent's own. The keys a run set are the ones it named at the call site, so passing the value your code already had still counts as the run asking for it.

`RunHooks.on_llm_start` and `RunConfig.call_model_input_filter` run between the prompt and the model request, so they see the managed prompt with the code's own tools and settings — and a filter that rewrites the instructions still has the last word.

## Known limits

- **`RunConfig(model=...)` skips everything but the instructions for that run.** The runner prefers a per-run model over the agent's own, and the agent's own is what this adapter installs — so the managed tools, settings and model do not reach that run, and nothing in a `Model` can see a `RunConfig` to say so. The prompt still applies, because it is applied where the agent assembles it. Use `agent_control(agent.clone(model=...))`, or `Runner.run(agent.clone(model=...))`, instead.
- **`RunConfig(model_provider=...)` is not consulted for a managed agent**, which resolves models itself. Pass your provider as `agent_control(agent, provider=...)`.
- **One config per agent, not per run.** `agent_control` is called once, where you build the agent.
- **Publishing an edit changes the cached prefix once**, the same as a redeploy would. Blocks are never reordered, and an added block lands after your last fixed block, so it stays inside the prefix a provider can cache.
- **A published value that reaches nothing costs only the piece containing it.** An unreachable Logfire, a missing value, or one this release cannot parse means the agent runs exactly as written; beyond that, an entry that matches nothing warns once per process, and `on_unmatched='error'` fails the request instead while `'ignore'` says nothing. What is *not* covered by that: a published block or tool description is model input like any other, so text published into one can change what the agent does, and `on_unmatched='error'` deliberately turns an unmatched entry into a failed request.
- **Publishing the baseline can lose a concurrent UI publish.** The variable is created rather than overwritten when it is missing, and re-read immediately before the write, but a value saved in the UI inside that round trip is overwritten by the older state. Set `publish_baseline=False` and create the variable in the UI where that window is not acceptable.

## TypeScript

There is no adapter for `@openai/agents` yet. It fits the same shape — one `Model` wrapper, whose `getResponse(request)` carries `systemInstructions`, `modelSettings`, and `tools` in a single object to rewrite, with the same rename remap on the way out and the same forward map on history. Two differences to plan for: the runner prefers the **agent's** model over `RunConfig.model` (the reverse of Python), so a per-run model override goes through `agent.clone({model})`; and there is no prefix router in core, so a `model` string only reaches the provider the user installed, and non-OpenAI models are `Model` objects rather than names.
