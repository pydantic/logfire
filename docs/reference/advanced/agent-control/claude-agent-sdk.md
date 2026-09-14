---
title: "Control a Claude Agent SDK agent from Logfire"
description: "Edit a Claude Agent SDK agent's system prompt, subagent prompts, model, thinking effort, and tool descriptions in Logfire, with no redeploy."
---
# Claude Agent SDK

Change what a [Claude Agent SDK](https://platform.claude.com/docs/en/agent-sdk/overview) agent tells the model without touching your source code: its system prompt, its subagents' prompts, its model, how hard it thinks, and the descriptions its in-process tools show the model, all edited in the Logfire UI and rolled out on the agent's next session.

This page is the adapter for that SDK. Everything it applies comes from [Agent Control](../agent-control.md), which owns the config shape, the Logfire variable it lives in, and the rules for what a published value may do. Read that page first if you have not: it explains versions, labels, rollouts, and what happens when Logfire is unreachable (your agent runs exactly as written).

!!! note "Install the extra"
    ```bash
    pip install 'logfire[agent-control-claude-agent-sdk]'
    ```

    It brings in Agent Control and the Claude Agent SDK.

You also need a Logfire project with variables enabled, and `logfire.configure()` called before the first session starts. The Logfire token comes from your project settings, the same one the rest of the SDK uses.

## Quick start

Wrap the `ClaudeAgentOptions` you already build, and pass what comes back to `query()` or `ClaudeSDKClient` instead:

```python skip-run="true" skip-reason="starts the claude CLI"
import asyncio
from typing import Any

from claude_agent_sdk import ClaudeAgentOptions, query, tool

import logfire
from logfire.agent_control.claude_agent_sdk import agent_control, sdk_mcp_server

logfire.configure()


@tool('refund_order', 'Refund an order.', {'order_id': str})
async def refund_order(args: dict[str, Any]) -> dict[str, Any]:
    return {'content': [{'type': 'text', 'text': f'Refunded {args["order_id"]}.'}]}


async def main() -> None:
    options = agent_control(
        ClaudeAgentOptions(
            system_prompt='You are a concise checkout assistant.',
            model='claude-sonnet-4-5',
            # Use `sdk_mcp_server` in place of `create_sdk_mcp_server` to keep tool definitions editable.
            mcp_servers={'shop': sdk_mcp_server('shop', tools=[refund_order])},
            allowed_tools=['mcp__shop__refund_order'],
        ),
        name='checkout_assistant',
    )
    async for message in query(prompt='Refund my last order.', options=options):
        print(message)


asyncio.run(main())
```

Call `agent_control` **last**, once your options say everything your code wants them to say: a published value is applied over them, and anything you change afterwards wins over Logfire.

**It returns a new `ClaudeAgentOptions` and never changes the one you passed**, neither the object, nor its `env` dictionary, nor its `mcp_servers` mapping. With nothing published for this agent it returns the very object you passed, unchanged.

### Name the agent yourself

The name is required and explicit. `ClaudeAgentOptions` has no name of its own, and the config is stored under the one you give (`agent__checkout_assistant`), so a name inferred from a Python variable would point the agent at a different config the day someone renames that variable. The name is kept as you wrote it for display and normalized for the variable key, so `checkout-assistant` and `Checkout Assistant` reach the same config.

### `agent_control(options, *, name=...)`

| Argument | |
|---|---|
| `options` | The `ClaudeAgentOptions` your code would start a session with. Optional: omitting it manages an agent that says nothing in code, so every section comes from Logfire. |
| `name` | Required. The agent's name, which its config is stored under as `agent__<name>`. |
| `label` | The label to resolve, such as `'production'`. `None` (the default) lets the variable's own targeting rules and rollout choose. |
| `on_unmatched` | What to do about a published entry this agent cannot apply: `'warn'` (the default, once per process per message), `'error'`, or `'ignore'`. |
| `publish_baseline` | Whether to publish the code baseline the Logfire editor diffs against. `True` by default. |
| `logfire_instance` | The Logfire instance to resolve and publish through. Defaults to the one `logfire.configure()` sets up. |

## What becomes editable in Logfire

| Source or canonical field | Block ID or runtime mapping | Editable | Conditions and unmatched behavior |
|---|---|---|---|
| **Instructions** | | | |
| `system_prompt='...'` (a string) | `system` | Yes | Removing the block sends `''`, which is what the SDK already sends for no custom prompt. |
| `system_prompt={'type': 'preset', ..., 'append': '...'}` | `append` | Yes | The `append` half only. Removing it sends the preset alone. |
| Claude Code's own preset prompt | `preset:claude_code` | No | The CLI renders it from your working directory, git status, and memory files, and never shows it to the SDK. Published as a dynamic block with no text; addressing it reports `dynamic-id`. |
| `system_prompt={'type': 'file', ...}` | `system:file` | No | The CLI reads the file itself. Published as a dynamic block with no text; addressing it reports `dynamic-id`. Edit the file. |
| `agents={'reviewer': AgentDefinition(prompt=...)}` | `agent:reviewer` | Text only | You can rewrite a subagent's prompt. You cannot remove the block: the CLI declares a subagent by its prompt and leaves one whose prompt is empty out of the session, so a removal would take the subagent, its description, and its tools away with it. The removal is reported and the code's prompt stays. An id no subagent carries reports `unknown-id`. |
| Added instructions (an entry with no id) | appended to `system` or to `append` | Conditional | Goes into the agent's own system prompt, or a preset's `append`. With a `system_prompt` file there is nothing in the options to append to, and the addition is reported. |
| `CLAUDE.md`, output styles, skills, plugins | | No | The CLI loads them, and they land in the conversation rather than the system prompt. Nothing addresses them, so nothing is reported. |
| **Model** | | | |
| `model` | `ClaudeAgentOptions.model` | Conditional | `anthropic:claude-sonnet-4-5`, an alias such as `anthropic:sonnet`, or a bare string with no `provider:` prefix. Any other provider is refused and reported: this SDK picks its provider from the CLI's environment, not from the model string. |
| Subagent `model` | | No | `AgentDefinition.model` is not a section of the config, so a published `model` never reaches it. |
| **Settings** | | | |
| `thinking` | `thinking` and `effort` | Yes | `false` sends `{'type': 'disabled'}`, `true` sends `{'type': 'adaptive'}`, and a level also sets `effort`. A published value sets both fields together, so `true` clears an `effort` your code set. `'minimal'` becomes `'low'`, the lowest level this CLI has. |
| `max_tokens` | `CLAUDE_CODE_MAX_OUTPUT_TOKENS` in `env` | Yes | The CLI stops the response there and reports the cap it read. |
| `timeout` | `API_TIMEOUT_MS` in `env` | Yes | Seconds, converted to whole milliseconds by Agent Control's own rounding. A value outside the representable range is dropped by the core and reported. |
| `temperature`, `top_p`, `top_k`, `seed`, `presence_penalty`, `frequency_penalty`, `parallel_tool_calls`, `stop_sequences` | | No | `ClaudeAgentOptions` has no such field, and the CLI chooses them itself. Each is reported as a setting this framework has no equivalent for. |
| `max_turns`, `max_budget_usd`, `permission_mode`, `betas` | | No | Not part of the config, so nothing can be published for them. |
| **Tools** | | | |
| In-process tools built with `sdk_mcp_server(...)` | `mcp__<server>__<tool>`, grouped under `toolset: <server>` | Yes | Name, description, and top-level parameter descriptions. Parameter names, types, requiredness, and the implementation stay code-defined. |
| In-process tools built with `create_sdk_mcp_server(...)` | | No | That helper keeps no reference to the definitions it was given, so there is nothing to rewrite. Such tools are not listed in the baseline, and an override naming one reports `unknown-tool`. Swap it for `sdk_mcp_server`, which takes the same arguments. |
| Built-in tools (`Read`, `Bash`, `Edit`, `Task`, and the rest) | | No | Their descriptions live inside the CLI binary. An override naming one reports `unknown-tool`. Restrict them with `allowed_tools` and `disallowed_tools` in code. |
| External MCP servers (stdio, SSE, HTTP) | | No | The CLI connects to them and lists their tools itself, so the SDK never sees a description. An override naming one reports `unknown-tool`. |
| Which tools exist at all | | No | A published config re-describes tools. It does not add or remove them. |

Every reported entry goes through `on_unmatched`: a `UserWarning` once per process by default, a `ValueError` under `'error'`, and nothing at all under `'ignore'`.

## When a published config applies

The Claude Agent SDK does not call the Messages API. It starts the `claude` CLI as a subprocess and talks JSON over its standard input and output, and the system prompt, the tool list, the model, and every sampling parameter are assembled *inside that process*. Nothing in the SDK, no hook, no callback, no transport, sees or can edit an outgoing model request.

So a published config is applied at the only seam there is, the `ClaudeAgentOptions` a session starts from, and **the unit of resolution is one session**. Publishing in Logfire takes effect on the next session your code starts, not on the next request of a session already running. Two consequences worth knowing:

- Call `agent_control` where you build the options for each `query()`, not once at import time, or a long-running process will never see anything you publish.
- Claude Code snapshots the rendered system prompt on a conversation's first request and reuses it verbatim, so a changed prompt does not reach a resumed conversation either. Pass `extra_args={'system-prompt-snapshot': 'off'}` if you need it to.

**Precedence** is code, then Logfire, then you: a published section is applied over what your options say, and anything you change on the returned object afterwards is the last word. A section nobody published is left exactly as your code wrote it.

## Put the config version on a whole run

`agent_control` resolves the config and returns, and you start the session afterwards, so the resolved label and version reach only the spans this adapter can still get inside: the hooks and the permission callback your options carry. To put them on a whole run, resolve and run inside one block with `ManagedAgent.session`:

```python skip-run="true" skip-reason="starts the claude CLI"
from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient

from logfire.agent_control.claude_agent_sdk import ManagedAgent

code_options = ClaudeAgentOptions(system_prompt='You are a concise checkout assistant.')
managed = ManagedAgent('checkout_assistant', label='production')


async def ask() -> None:
    with managed.session(code_options) as options:  # spans inside carry the config version
        async with ClaudeSDKClient(options=options) as client:
            await managed.refresh_model(client, code_options)  # a model published since connecting
            await client.query('Refund my last order.')
            async for message in client.receive_response():
                print(message)
```

`code_options` stays the options your *code* built, and it is what both calls are given. Applying a managed config to an already-managed object would add a second copy of any anonymous instruction block, and `refresh_model` reads the model to fall back to from what it is passed, so handing it managed options would make a withdrawn config roll back to the managed model instead of yours.

## What the Logfire editor opens on

The **baseline**, what your code says today, is published as the variable's `example` the first time an agent is configured in a process, so the editor opens on your prompt, block by block, rather than on a blank form. It is never resolved and never applied. Everything this SDK can be told is plain data on `ClaudeAgentOptions`, so the baseline describes the code rather than one observed request. A value Agent Control cannot describe, such as `effort='max'`, which is not `'xhigh'`, is left out of it and warned about rather than approximated.

!!! warning "Publishing the baseline writes to the variable"
    A value saved in the Logfire UI during that one round trip can be lost. Pass `publish_baseline=False` and create the variable in the UI if your deployment cannot tolerate that.

## What a rename changes, and what it does not

Your tool function is untouched and is never told a name: the SDK dispatches on the name the model called and hands your handler the same arguments. Parameter *names* are never renamed, only their descriptions, so arguments arrive exactly as your code declares them.

The model-facing name of an in-process tool is `mcp__<server>__<name>`, and everything that refers to a tool is keyed on it. Those references are rewritten together with the definition:

| Reference | What a rename does |
|---|---|
| `allowed_tools`, `disallowed_tools` | Rewritten, keeping any `(specifier)` as written. |
| `AgentDefinition.tools`, `AgentDefinition.disallowedTools` | Rewritten, so a subagent keeps the tool it was allowed. |
| `permission_prompt_tool_name` | Rewritten when it names a renamed tool. |
| Hook matchers naming a tool exactly, `A\|B` alternations included | Rewritten. |
| Hook matchers written as a pattern | Left as written. One that matched the old name and does not match the new one is reported through `on_unmatched`: rewriting a regular expression would mean editing one on a guess, and a `PreToolUse` hook that quietly stops running is a permission check that quietly stops happening. |
| `can_use_tool(tool_name, ...)` | Called with the name **your code** gave the tool, and the CLI's suggested permission rules are translated the same way. Rules the callback asks to add come back out in the names the CLI knows. |
| Hook callbacks | Called with `tool_name` set to the name **your code** gave the tool. Everything else in the payload is what the CLI sent. |
| Two servers with the same tool name | A name is only taken inside its own server, since the model-facing name carries the server. Renaming the shop's `search` to `lookup` does not collide with the CRM's `lookup`. A rename onto a name already advertised *by the same server* is dropped, that override's other patches still apply, and the collision is reported. |

Two things a rename does reach that this adapter cannot follow, both because they happen inside the CLI process:

- **The conversation transcript.** The tool calls the CLI writes to its transcript, what `--resume` and `--continue` replay and what the model is shown on the next turn, carry the managed name. A session resumed after you change or withdraw a rename contains calls under a name the current tool list does not have.
- **The message stream.** `ToolUseBlock.name` on the messages `query()` yields is the name the model called, so code that reads the stream sees the managed name. The name your handler, your hooks, and your permission callback see is the code-side one.

## Known limits

- **Only in-process servers built with `sdk_mcp_server` are editable.** The order of `mcp_servers` becomes the order the model is shown the tools in: a rebuilt server keeps its position, and unpatched tools keep their exact definitions.
- **A tool edit invalidates the prompt cache.** The tool list sits ahead of the system prompt in the cached prefix, so renaming or re-describing any tool invalidates it for every session that starts afterwards. So does switching models with `refresh_model`.
- **`refresh_model` sends only the model.** It does not re-apply instructions, settings, or tools, because the CLI has already been started with those.
- **Hooks and the permission callback are wrapped.** The objects on the returned options are not the functions you passed. They call yours with the names above, and re-establish the resolved config's telemetry around it.
- **The CLI's own telemetry does not carry the agent name.** The agent's identity in Logfire is the `name` you pass. Set `OTEL_RESOURCE_ATTRIBUTES` in `env` yourself if you want the CLI's spans to carry it too.
- **Nothing about reading a config can crash a session.** An unreachable Logfire, a missing value, or one this release cannot parse all mean the same thing: the agent runs exactly as written. Beyond that, a value Agent Control cannot act on costs only the piece containing it, unless you asked for `on_unmatched='error'`, which raises instead. What a published value *says* is still yours to get right: a model id no provider knows fails the session the same way writing that id in your code would, so roll a model change out to a slice of traffic first.

## Verify

Start one session with `agent_control` in place. In Logfire you should now see a variable called `agent__<your agent name>` whose example is your agent's own prompt, model, and tool descriptions, block by block. Publish a change to the `system` block, run the agent again, and the next session sends the published text.

To see which version produced a run, start the session inside `ManagedAgent.session(...)` as above: every span the block emits then carries `logfire.variables.agent__<name>` and `logfire.variables.agent__<name>.version`. With `agent_control` alone those attributes reach only the spans of the hooks and permission checks the options carry, since the session itself starts after the call returns.

## Troubleshooting

**Nothing you publish reaches the agent.** The config is read when `agent_control` is called. A process that calls it once at import time keeps the first answer forever. Move the call to where you build the options for each session.

**A published change reaches a new conversation but not a resumed one.** Claude Code reuses the system prompt it snapshotted on the conversation's first request. Pass `extra_args={'system-prompt-snapshot': 'off'}`.

**A tool override warns `unknown-tool`.** The tool is not one this adapter can rewrite: a built-in, one from an external MCP server, or one from a server built with `create_sdk_mcp_server`. Only the last is fixable, by building the server with `sdk_mcp_server` instead.

**A published `model` warns and does not apply.** The model string names a provider other than `anthropic`. This SDK takes an Anthropic model id and chooses its provider from the environment the CLI runs in, so publish `anthropic:<model>` or a bare model id.

## Next steps

- [Agent Control](../agent-control.md): the config shape every adapter reads, and what a published value may do to any agent.
- [Instrument the Claude Agent SDK](../../../integrations/llms/claude-agent-sdk.md): the traces that show what the agent did with the config you published.
- [Managed Variables](../managed-variables/index.md): the versions, labels, rollouts, and targeting Agent Control is built on.
