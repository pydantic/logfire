---
title: "Use Agent Sandboxes with Pydantic AI"
description: "Let a Pydantic AI agent call its tools from Python scripts that run in Logfire Agent Sandboxes, with one capability."
---

# Use Agent Sandboxes with Pydantic AI

!!! info "Experimental"
    Agent Sandboxes is experimental and available to selected Logfire organizations. Email
    [engineering@pydantic.dev](mailto:engineering@pydantic.dev) if you want to try it.

Let a [Pydantic AI](https://pydantic.dev/docs/ai/overview/) agent answer a question with one Python script instead of many tool calls.
You keep your tools as they are. Pydantic AI's **Code Mode** (a capability that turns an agent's tools into functions
the model can call from Python) gives the model one `run_code` tool, and Agent Sandboxes runs each script.

Code Mode writes the type stubs from your tools, checks each script against them, sends errors back to the model, and
records every run in Logfire. You add one argument.

!!! warning "Scripts and tool results leave your application"
    Scripts, tool arguments, and results pass through Logfire for execution. Hosted telemetry can record this content
    in your project. See [tracing and storage](limits.md#understand-tracing-and-storage).

## Before you start

- Follow [Run code from Python](python.md) to set `LOGFIRE_API_KEY` to a key with permission to run
  code in agent sandboxes.
- Set `OPENAI_API_KEY` to a key from the [OpenAI API keys page](https://platform.openai.com/api-keys).
  The example sends model requests to OpenAI.
- Install Logfire with the `agent-sandboxes` extra, and Pydantic AI Harness with the `codemode` extra:

```bash
pip install 'logfire[agent-sandboxes]>=5.4.0' 'pydantic-ai-harness[codemode]>=0.62.0'
```

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
    'openai:gpt-6.1-sol',
    tools=[list_customers, get_request_stats, list_open_tickets],
    capabilities=[
        CodeMode(
            monty_sandbox=logfire.agent_sandboxes,
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

Pass the function itself, not `logfire.agent_sandboxes()`.
Code Mode calls it on the first `run_code` call of each agent run, so concurrent runs each get their own pool.
No connection opens until the model first calls `run_code`.

## What the model writes

The model sees one tool, `run_code`, with your three tools listed as Python functions. For the question above it writes
short scripts like the ones on [Answer questions that need dozens of tool
calls](many-tool-calls.md#see-the-code-the-agent-writes). They fetch the enterprise customers, fetch each customer's
request counts, compute availability in Python, and return only the customers that
missed their target. Each script continues from the variables of the one before it. The exact code changes from run
to run.

A script can also run several calls at once with `asyncio.gather`.
Each call is still a separate round trip between the sandbox and your process.
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

- **`UserError: `monty_sandbox` takes a URL or a function that returns the pool, not the pool itself`**: you passed
  `logfire.agent_sandboxes()`. Pass `logfire.agent_sandboxes` without the parentheses.
- **`UserError` that mentions `monty_sandbox_url`**: `monty_sandbox_url` is the deprecated form of `monty_sandbox`.
  Pass only `monty_sandbox`.
- **`LogfireConfigError: Agent sandboxes require a Logfire API key`**: the run started without an API key. Set
  `LOGFIRE_API_KEY`, or pass `api_key` to `logfire.configure()`.
- **The model calls a tool directly instead of from `run_code`**: Code Mode keeps some tools outside the sandbox, such as
  tools that load lazily. See [Selective tool sandboxing](https://pydantic.dev/docs/ai/harness/code-mode/#selective-tool-sandboxing).

## Next steps

- [Work with large tool results](large-results.md): tools that return more rows than the model should read.
- [What sandbox code can do](limits.md): the parts of Python that scripts can use.
- [Code Mode](https://pydantic.dev/docs/ai/harness/code-mode/): every Code Mode option, in the Pydantic AI docs.
