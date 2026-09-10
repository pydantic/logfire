# Agent Control for Google ADK

Wrap a [Google ADK](https://google.github.io/adk-docs/) `LlmAgent` with `agent_control` and its instructions, its model, its model settings, and the descriptions its tools show the model become editable in the Logfire UI: versioned, labelled, rolled out to a percentage of traffic, and rolled back as one unit, without a redeploy.

Everything you don't change in Logfire keeps doing what your code says, and removing a change there puts that piece back. There is no third state. The [Agent Control overview](index.md) covers the config shape, what a published value can and cannot do, and the guarantees all of this rests on; this page is the ADK-specific half.

You need a Logfire project and an [API key](../managed-variables/index.md#api-keys) with the `project:read_variables` scope, set as `LOGFIRE_API_KEY`. Publishing the baseline also needs `project:write_variables`; without it, pass `publish_baseline=False` and create the variable in the UI yourself.

!!! note "Install the agent-control-google-adk extra"
    ```bash
    pip install 'logfire[agent-control-google-adk]'
    ```

## Quickstart

```python skip-run="true" skip-reason="runs a real agent"
import asyncio

from google.adk.agents import LlmAgent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

import logfire
from logfire.agent_control.google_adk import agent_control

logfire.configure()


def get_weather(city: str) -> str:
    """Get the current weather for a city."""
    return f'It is sunny in {city}.'


agent = agent_control(
    LlmAgent(
        name='checkout_assistant',
        description='Handles refunds.',
        model='gemini-2.5-flash',
        instruction='You are a concise checkout assistant.',
        tools=[get_weather],
    ),
    label='production',
)


async def main() -> None:
    sessions = InMemorySessionService()
    session = await sessions.create_session(app_name='checkout', user_id='u1')
    runner = Runner(app_name='checkout', agent=agent, session_service=sessions)
    message = types.Content(role='user', parts=[types.Part(text='What is the weather in London?')])
    async for event in runner.run_async(user_id='u1', session_id=session.id, new_message=message):
        if event.content and event.content.parts:
            print(''.join(part.text or '' for part in event.content.parts))
    await runner.close()


asyncio.run(main())
```

The config is keyed on `agent.name` — ADK requires one and validates it, so there is nothing extra to name — and lives in the Logfire variable `agent__checkout_assistant`.

The baseline is published from the agent's **first model request**, so it reaches Logfire once the agent has actually run, which is what the `Runner` above is doing. That snapshot is what the editor shows you as the code side, so you open on your own prompt, block by block, rather than on a blank form.

## `agent_control`

```python skip="true" skip-reason="signature"
agent_control(
    agent,
    *,
    name=None,
    label=None,
    on_unmatched='warn',
    publish_baseline=True,
    logfire_instance=None,
)
```

It returns **the same `LlmAgent`**, wired up in place rather than copied, so a reference someone else already holds is managed too. Three things on the agent are replaced:

| What | How |
|---|---|
| `before_model_callback` | The managed callback is prepended to the agent's own. |
| `after_model_callback` | The managed callback is prepended to the agent's own. |
| `model` | Wrapped in a `BaseLlm` that delegates to it, so a published model can change the class serving a request. Only when the agent names a model: one that inherits its parent's is left alone. |

| Argument | Meaning |
|---|---|
| `agent` | The agent to manage. Its `name` is what the config is keyed on. |
| `name` | Key the config on this instead of `agent.name`. |
| `label` | The label to resolve, such as `'production'`. When `None`, the variable's own targeting rules and rollout choose which label this process gets. |
| `on_unmatched` | What to do with a published value that reaches nothing here. `'warn'` (the default) says so once per process, `'error'` fails the request, `'ignore'` says nothing. Every row below says what "reaches nothing" means for that piece. |
| `publish_baseline` | Whether to publish what this adapter can see of the agent as the variable's example. Turn it off when the deployment's token is deliberately read-only. |
| `logfire_instance` | The Logfire instance to resolve and publish through. Defaults to the global one that `logfire.configure()` sets up. |

## What becomes editable

### Instructions

ADK joins every instruction source into one string before any hook sees it, so the adapter finds each block by looking for its text on the `"\n\n"` seams that join is made of.

| Source | Block id | Editable | Conditions, and what `on_unmatched` sees |
|---|---|---|---|
| `instruction` (a string) | `agent` | **Yes** | One containing `{state}` placeholders is located but refused, as a dynamic block: replacing it would pin one request's rendering forever. |
| `instruction` (an `InstructionProvider` callable) | `agent` | **No** | Its text is computed per request. The editor is shown that the block exists; addressing it is reported. |
| `static_instruction` | `static` | **Conditional** | Only when it is text — a `str`, or `Content`/`Part`s that are all text. One carrying an image or a file is described as dynamic and never matched. **Setting a `static_instruction` also moves `instruction` out of the system prompt into the request's user content**, which this adapter's system-instruction hook cannot edit: the `agent` block then goes unlocated, and an entry addressing it is reported rather than applied. |
| `global_instruction` on the root agent | `global` | **Yes** | ADK deprecates it in favour of `GlobalInstructionPlugin`, which is installed on the `App` and is *not* visible here. |
| The identity line ADK writes (`You are an agent. Your internal name is …`) | `identity` | **Yes** | Editing `description` on its own is not possible: ADK folds it into that line, so the line is what you replace. A single-turn agent has no such line, and addressing it is reported. |
| Text a tool or the planner appends | none | **No** | ADK gives it no name to address it by. It is left exactly where it was. |
| An added block | none needed | **Yes** | An entry with no `id` lands at the end of the prompt's static prefix — after your own text, ahead of whatever the planner and the tools append — so published text stays inside the prefix a provider can cache. |
| A block something ahead of this hook has rewritten | — | **No** | The managed callback runs first, so this means a plugin's callback. The block goes unlocated, and an entry addressing it is reported. |

A config that publishes no `instructions` at all leaves the assembled prompt untouched: the object ADK built, not a re-join of this adapter's partition of it.

### Model

| Canonical field | Runtime mapping | Editable | Conditions, and what `on_unmatched` sees |
|---|---|---|---|
| `model` | `llm_request.model`, and the `BaseLlm` class serving the request | **Yes**, across providers included | Publish `provider:model` (`anthropic:claude-fable-5-1`) or an ADK-native name (`gemini-2.5-flash`, or a `Class:model` override). `google`, `google-cloud` and `anthropic` reach ADK's own registry; every other provider becomes LiteLLM's `provider/model`. A name ADK cannot route — including one whose provider extra this deployment has not installed — is reported, and the agent keeps the model it was written with. |
| `model`, on an agent that inherits it from its parent | — | **No** | Give the sub-agent an explicit `model=` to manage it. Resolving an inherited model when the agent is wrapped would pin whatever the tree said at that moment, so a published `model` is reported instead. |

`google` (the Gemini API) and `google-cloud` (Vertex AI) are the provider ids Pydantic AI v2 uses, and they are what a baseline published from here names. The v1 spellings `google-gla` and `google-vertex` are still **accepted** on the way in, so a config published against a v1-era agent keeps working.

### Model settings

Every setting is written into the request's `GenerateContentConfig`, and **what the model serving that request does with it decides whether the setting applies at all**. One that would not apply is left off the request and reported, rather than set where Logfire can see it and the model cannot. A model class this adapter does not recognise is assumed to read everything ADK's own Gemini client does, which is the one case where a published setting can go unapplied without a word.

| Canonical setting | `GenerateContentConfig` field | Gemini | Claude | LiteLLM |
|---|---|---|---|---|
| `max_tokens` | `max_output_tokens` | yes | yes | yes |
| `temperature` | `temperature` | yes | yes | yes |
| `top_p` | `top_p` | yes | yes | yes |
| `top_k` | `top_k` | yes | yes | yes |
| `stop_sequences` | `stop_sequences` | yes | yes | yes |
| `seed` | `seed` | yes | no | no |
| `presence_penalty` | `presence_penalty` | no | no | yes |
| `frequency_penalty` | `frequency_penalty` | no | no | yes |
| `timeout` | `http_options.timeout`, in milliseconds | yes | no | yes |
| `thinking`: `true` | `thinking_config.thinking_budget`, automatic | yes | yes | no |
| `thinking`: `false` | `thinking_config`, a minimal level or a zero budget | yes | yes | no |
| `thinking`: `minimal` / `low` / `medium` / `high` | `thinking_config.thinking_level` | Gemini 3 and later | no | no |
| `parallel_tool_calls` | — | no | no | no |

- **The two penalties are `GenerateContentConfig` fields that no Gemini model accepts.** ADK forwards them; the Gemini API answers `400 Penalty is not enabled for models/<name>`, on every model tried. A published setting that fails the request is worse than one that is ignored, so they are left off a Gemini request and reported. LiteLLM maps both.
- **Gemini's two generations ask for thinking differently, and each refuses the other's spelling.** Gemini 2.5 has no `thinking_level`; Gemini 3 refuses a zero `thinking_budget`. So `thinking: false` is sent as a zero budget to a Gemini 2 model and as `thinking_level: MINIMAL` to a Gemini 3 one, chosen from the model's name. `thinking: true` is an automatic budget, which both accept. A named level published for a Gemini 2 model is reported rather than sent.
- `thinking: 'xhigh'` has no level in ADK at all, and is reported rather than rounded down to `high`.
- A published `thinking` replaces a `BuiltInPlanner`'s own thinking config outright: a published effort left next to the planner's budget would be neither of the two values.
- `parallel_tool_calls` has no `GenerateContentConfig` field, and the one backend that can express it (LiteLLM) takes it when the model object is constructed, which no per-request hook reaches.
- Claude also ignores `temperature`, `top_p` and `top_k` whenever thinking is on. ADK warns about that combination itself, and this adapter does not try to predict it.

### Tools

| Piece | Runtime mapping | Editable | Conditions, and what `on_unmatched` sees |
|---|---|---|---|
| `description` | The tool's `FunctionDeclaration` on the request | **Yes** | For every tool the model is shown a declaration for. |
| Parameter descriptions | Top-level properties of that declaration's schema | **Yes** | A tool built from a plain Python function has no parameter descriptions of its own — ADK does not read a docstring's `Args:` section — so publishing one *adds* a description the model never had. A patch naming a parameter the tool does not have is reported. |
| `new_name` | The declaration, and every other place the model is told a name; see below | **Yes** | A rename onto a name another tool already advertises is dropped and reported, while that override's other patches still apply, so every tool keeps a name the model can call. |
| Parameter names, types, requiredness, and what the tool does | — | **No, ever** | Only what the model is told changes. |
| Provider-side tools (Google Search, code execution, URL context, a provider-hosted MCP server) | — | **No** | These carry no function declaration, so the model is shown no name or description for this adapter to patch, and nothing dispatches them back into your code. An override naming one is reported as a tool this agent does not advertise. ADK's own `MCPToolset` is *not* one of these: its tools resolve to ordinary declarations and are managed like any other. |
| Toolset grouping | `toolset`, in the baseline and in an override | **Conditional** | A `BaseToolset` is grouped under its `tool_name_prefix`. Without one it is grouped under its class name, but only when the agent has exactly one toolset of that class: two `MCPToolset`s side by side are left ungrouped rather than shown as one group an override cannot address. A toolset that cannot list itself during a request is ungrouped for that request. |

## When the config applies

**Per model request.** Every request the agent makes — the first one, and each one after a tool result — resolves the published config and applies it, so a value saved in Logfire takes effect on the next request without a restart. A rollout can therefore land differently on two requests of one run.

**Precedence is code, then published, then this run.** Your own `before_model_callback`s run *after* the managed one, so anything you set for a single run wins over the published config.

**Telemetry.** Spans emitted inside the model call carry the label and version that produced it. ADK opens its own `call_llm` and `execute_tool` spans *before* any callback this adapter can install, so those two are not themselves attributed — see [Known limits](#known-limits).

**The baseline** is published once per process, from the first request, off the request's thread, and can neither delay nor fail a request. It is published as an *observation* rather than as a reading of the code, and the variable Logfire creates says so: the tool list and the prompt's seams are the ones that request carried. It describes the instruction blocks with their ids (dynamic ones carrying no text), the agent's model in canonical form, every tool with every top-level parameter, and the settings the agent's own model actually reads — including the thinking a `BuiltInPlanner` contributes, which is what the agent really does. Publishing it can lose a value saved in the Logfire UI in the same instant; the [overview](index.md) has the exact window, and `publish_baseline=False` opts out of it.

## What your code sees when a tool is renamed

**Your code sees the name your code gave the tool.** The rename stops at the model boundary:

- the model is shown the managed name — in the tool list, in a forced `tool_config.function_calling_config.allowed_function_names`, and in the calls and responses replayed to it from earlier turns;
- the call it makes is translated back before ADK dispatches it, so `llm_request.tools_dict`, `before_tool_callback`, `BaseTool.name`, and the events your session persists all say `get_weather`;
- your tool function is untouched, and so is the agent's own tool object.

Because history is persisted in your code's names, **changing or withdrawing a rename mid-conversation is safe**: earlier turns are translated into whatever is published now, so the model never sees a call naming a tool that is missing from the tool list beside it.

Two things this does not do. A conversation whose events were persisted by an *earlier* deployment that wrote managed names is not repaired: there is no versioned mapping, and guessing at one would rename a call this deployment cannot identify. And a call to a tool the agent no longer advertises at all keeps its code name in the replay, because there is nothing left to translate it into.

## Known limits

- **The prompt is matched by text.** A block whose text this adapter cannot reproduce, or that something ahead of it has rewritten, is left alone and reported rather than replaced. Text is matched only on ADK's own join seams, so a source that also occurs *inside* another block is still matched at its own position.
- **`GlobalInstructionPlugin` is invisible here.** It is installed on the `App` rather than on the agent, so the text it prepends cannot be addressed. The deprecated `global_instruction` field on the root agent can be.
- **A `static_instruction` moves your `instruction` out of reach.** ADK sends it as user content, and this adapter edits the system instruction. The `static` block itself stays editable.
- **Wrapping the model changes its class.** `agent.model` becomes a wrapper that delegates to your model, which is what makes a cross-provider switch possible at all. Code that checks `isinstance(agent.canonical_model, Gemini)` will not recognise it. What the model *reports* — its name and its capabilities — is forwarded unchanged, which also means a request is shaped by the **code** model's capabilities even when a published model serves it: ADK asks the agent's model what it supports while assembling the request, before any hook can say which model will get it. A published model that reports different capabilities is switched to anyway, and reported under `on_unmatched`, since the request it inherits was built for something else.
- **ADK's own `call_llm` and `execute_tool` spans are not config-attributed.** Both are opened before the callbacks this adapter can install, and the label and version travel as baggage, which only reaches spans started inside it. Everything the model call emits is attributed; a tool's own span is not.
- **Live (bidirectional) runs are not managed.** ADK builds a live connection from the agent's model rather than from a per-request name, so a live agent connects exactly as written.
- **Failing to resolve is not failing to run.** An unreachable Logfire, a missing value, or one this release cannot parse all mean the same thing: the agent runs exactly as written. What can still stop a request is a deliberate `on_unmatched='error'`, which is what it is for.

## Next steps

- [Agent Control](index.md): the config shape, the guarantees, and how to write an adapter for another framework.
- [Managed Variables](../managed-variables/index.md): the versions, labels, rollouts, and targeting this is built on.
- [A/B Testing](../managed-variables/ab-testing.md): splitting traffic between two configs and comparing them in traces.
