---
title: "Use Agent Sandboxes with Pydantic AI"
description: "Let a Pydantic AI agent call its tools from Python scripts that run in Logfire Agent Sandboxes, with one capability."
---

# Use Agent Sandboxes with Pydantic AI

!!! info "Experimental"
    Agent Sandboxes is available to selected Logfire organizations. See [access and availability](index.md).

Let a [Pydantic AI](https://pydantic.dev/docs/ai/overview/) agent answer a question with one Python script instead of many tool calls.
You keep your tools as they are. Pydantic AI's **Code Mode** (a capability that turns an agent's tools into functions
the model can call from Python) gives the model one `run_code` tool, and Agent Sandboxes runs each script.

Code Mode writes the type stubs from your tools, checks each script against them, sends errors back to the model, and
records every run in Logfire. You add one argument.

!!! warning "This integration requires an unreleased Pydantic AI change"
    The `monty_pool_factory` support shown here depends on
    [Pydantic AI PR #11179](https://github.com/pydantic/pydantic-ai/pull/11179). It is not in a released Harness version.
    The example below requires a development build that includes that change.
    Use [Add a code tool to any agent](any-framework.md) with released Pydantic AI versions.

!!! warning "Scripts and tool results leave your application"
    Scripts, tool arguments, and results pass through Logfire for execution. Default client instrumentation also
    records them in your project. See [tracing and storage controls](limits.md#control-client-tracing).

## Before you start

- Follow [Run code from Python](python.md) to set `LOGFIRE_API_KEY` to a key with permission to run
  code in agent sandboxes.
- Set `ANTHROPIC_API_KEY` to a key from the [Claude Console API keys page](https://platform.claude.com/settings/keys).
  The example sends model requests to Anthropic.
- Install Logfire with the `agent-sandboxes` extra:

```bash
pip install 'logfire[agent-sandboxes]'
```

Install a development build of Pydantic AI Harness with the `codemode` extra that includes the change linked above.
A regular `pip install pydantic-ai-harness` does not yet provide the required integration.

## Run the agent's code in Agent Sandboxes

Add `CodeMode` to the agent's capabilities, and pass `logfire.agent_sandboxes` as the function that creates the
sandbox pool:

```python title="agent.py" hl_lines="14-16" skip-run="true" skip-reason="external-connection"
from pydantic_ai import Agent
from pydantic_ai_harness import CodeMode
from tools import get_request_stats, list_customers, list_open_tickets

import logfire

logfire.configure()
logfire.instrument_pydantic_ai()

agent = Agent(
    'anthropic:claude-sonnet-4-5',
    tools=[list_customers, get_request_stats, list_open_tickets],
    capabilities=[
        CodeMode(
            monty_pool_factory=logfire.agent_sandboxes,
        )
    ],
)

result = agent.run_sync(
    'Which enterprise customers missed their availability target (successful requests / all requests) '
    'over the last 7 days, and which of them have open support tickets?'
)
print(result.output)
```

`tools.py` is the file from [Answer questions that need dozens of tool calls](many-tool-calls.md#write-your-tools-as-normal-python-functions).

Code Mode calls `logfire.agent_sandboxes()` once for each agent run, so concurrent runs each get their own pool. The
pool connects only when the model first calls `run_code`.

## What the model writes

The model sees one tool, `run_code`, with your three tools listed as Python functions. For the question above it writes
short scripts like the ones on [Answer questions that need dozens of tool
calls](many-tool-calls.md#see-the-code-the-agent-writes). They fetch the enterprise customers, fetch each customer's
request counts in parallel with `asyncio.gather`, compute availability in Python, and return only the customers that
missed their target. Each script continues from the variables of the one before it. The exact code changes from run
to run.

Your tools run in your process, as they would without Code Mode. Only the script runs in the sandbox.

## Keep the sandbox's variables across conversation turns

Each agent run starts a new session. To let a later turn use the variables an earlier turn defined, pass a `repl_store`
to `CodeMode`. Code Mode saves the session at the end of each run and loads it at the start of the next run in the same
conversation. See [Keep the REPL (read-eval-print loop) across runs](https://pydantic.dev/docs/ai/harness/code-mode/#keep-the-repl-across-runs) in
the Pydantic AI docs, and [Keep an agent's work across conversation turns](conversations.md) for how this works.

## Verify it worked

Run `python agent.py`, then open the [Live view](../guides/web-ui/live.md). You should see the agent run's **trace**
(the full journey of one request, made of nested spans). Inside it, find the `run_code` tool call. It contains a
`run code` span with the script the model wrote, and a span for each tool the script called.

## Troubleshooting

- **`UserError` that mentions `monty_sandbox_url`**: set either `monty_pool_factory` or `monty_sandbox_url`, not both.
- **`LogfireConfigError: Agent sandboxes require a Logfire API key`**: the run started without an API key. Set
  `LOGFIRE_API_KEY`, or pass `api_key` to `logfire.configure()`.
- **The model calls a tool directly instead of from `run_code`**: Code Mode keeps some tools outside the sandbox, such as
  tools that load lazily. See [Selective tool sandboxing](https://pydantic.dev/docs/ai/harness/code-mode/#selective-tool-sandboxing).

## Next steps

- [Work with large tool results](large-results.md): tools that return more rows than the model should read.
- [What sandbox code can do](limits.md): the parts of Python that scripts can use.
- [Code Mode](https://pydantic.dev/docs/ai/harness/code-mode/): every Code Mode option, in the Pydantic AI docs.
