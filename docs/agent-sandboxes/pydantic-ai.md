---
title: "Use Agent Sandboxes with Pydantic AI"
description: "Let a Pydantic AI agent call its tools from Python scripts that run in Logfire Agent Sandboxes, with one capability."
---

# Use Agent Sandboxes with Pydantic AI

!!! info "Beta"
    Agent Sandboxes is in beta on Logfire Cloud. If you do not see **Agent Sandboxes** in your project, see
    [Enable Agent Sandboxes](python.md#enable-agent-sandboxes).

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
pip install 'logfire[agent-sandboxes]>=5.6.0' 'pydantic-ai-harness[codemode]>=0.67.0'
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

Run `python agent.py`. For the sample data, a correct answer names Customer 9, Customer 42, Customer 87, and
Customer 111 as below their target, and Customer 42 and Customer 87 as the ones with open tickets.

## What the model writes

The model sees one tool, `run_code`, with your three tools listed as Python functions. It does not call your tools
one at a time. It writes scripts like this one, and each script continues from the variables of the one before it:

```python skip="true" skip-reason="sandbox-code"
import asyncio

customers = await list_customers(plan='enterprise')
stats_lists = await asyncio.gather(*[get_request_stats(customer_id=c['id'], days=7) for c in customers])
missed = []
for c, rows in zip(customers, stats_lists):
    total = sum(r['requests'] for r in rows)
    errors = sum(r['errors'] for r in rows)
    if total and (total - errors) / total < c['target']:
        missed.append(c)
[c['name'] for c in missed]
```

The exact code changes from run to run. This script makes 41 tool calls and reads 1,680 rows, and it returns four
names to the model. Your tools run in your process, as they do without Code Mode. Only the script runs in the sandbox.

In three runs of this question, the agent was correct each time and used a median of 4,680 input tokens. With plain
tool calls, the same agent was correct in one run of three and used 111,162. See
[the full comparison](many-tool-calls.md#what-this-changes), which includes a smaller model and the limits of the test.

## Keep the sandbox's variables across conversation turns

Each agent run starts a new session. To let a later turn use the variables an earlier turn defined, pass a `repl_store`
to `CodeMode`. Code Mode saves the session at the end of each run and loads it at the start of the next run in the same
conversation. See [Keep the REPL (read-eval-print loop) across runs](https://pydantic.dev/docs/ai/harness/code-mode/#keep-the-repl-across-runs) in
the Pydantic AI docs, and [Keep an agent's work across conversation turns](conversations.md) for how this works.

With Agent Sandboxes, the state that Code Mode saves is the ID of a snapshot that Logfire stores.
Logfire keeps it for 7 days, so a conversation that resumes later than that starts with a fresh session.

## Verify it worked

Run `python agent.py`, then open the [Live view](../guides/web-ui/live.md). You should see the agent run's trace.
Inside it, find the `run_code` tool call. It contains a
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
