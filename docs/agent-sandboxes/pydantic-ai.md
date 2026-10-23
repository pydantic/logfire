---
title: "Use Agent Sandboxes with Pydantic AI"
description: "Let a Pydantic AI agent call its tools from Python scripts that run in Logfire Agent Sandboxes, with one capability."
---

# Use Agent Sandboxes with Pydantic AI

Let a [Pydantic AI](https://pydantic.dev/docs/ai/overview/) agent answer a question with one Python script instead of many tool calls.
You keep your tools as they are. Pydantic AI's **Code Mode** (a capability that turns an agent's tools into functions
the model can call from Python) gives the model one `run_code` tool, and Agent Sandboxes runs each script.

Code Mode writes the type stubs from your tools, checks each script against them, sends errors back to the model, and
records every run in Logfire. You add one argument.

## Before you start

- Follow [Run code from Python](python.md) to set `LOGFIRE_API_KEY` to a key with permission to run
  code in agent sandboxes.
- Install Logfire with the `agent-sandboxes` extra, and Pydantic AI Harness with the `codemode` extra:

```bash
pip install 'logfire[agent-sandboxes]' 'pydantic-ai-harness[codemode]'
```

## Run the agent's code in Agent Sandboxes

Add `CodeMode` to the agent's capabilities, and pass `logfire.agent_sandboxes` as the function that creates the
sandbox pool:

```python title="agent.py" hl_lines="14-16" skip-run="true" skip-reason="external-connection"
import logfire
from pydantic_ai import Agent
from pydantic_ai_harness import CodeMode

from tools import get_availability, list_customers, list_open_tickets

logfire.configure()
logfire.instrument_pydantic_ai()

agent = Agent(
    'anthropic:claude-sonnet-4-5',
    tools=[list_customers, get_availability, list_open_tickets],
    capabilities=[
        CodeMode(
            monty_pool_factory=lambda: logfire.agent_sandboxes(request_timeout=40),
        )
    ],
)

result = agent.run_sync(
    'Which enterprise customers missed their availability target in the last 7 days, '
    'and which of them have open support tickets?'
)
print(result.output)
```

`tools.py` is the file from [Answer questions that need dozens of tool calls](many-tool-calls.md#write-your-tools-as-normal-python-functions).

Code Mode calls `logfire.agent_sandboxes()` once for each agent run, so concurrent runs each get their own pool. The
pool connects only when the model first calls `run_code`.

`request_timeout=40` gives each script up to 40 seconds between calls to your tools. The default, 10 seconds, is less
than Code Mode's own 30-second limit for a script. With the default, a slow script loses its connection instead of
getting Code Mode's clearer time-limit error.

## What the model writes

The model sees one tool, `run_code`, with your three tools listed as Python functions. For the question above it writes
one script, like the one on [Answer questions that need dozens of tool
calls](many-tool-calls.md#see-the-script-your-agent-writes): it fetches the enterprise customers, checks their
availability in parallel with `asyncio.gather`, and returns only the customers with open tickets. The exact code
changes from run to run.

Your tools run in your process, as they would without Code Mode. Only the script runs in the sandbox.

## Keep the sandbox's variables across conversation turns

Each agent run starts a new session. To let a later turn use the variables an earlier turn defined, pass a `repl_store`
to `CodeMode`. Code Mode saves the session at the end of each run and loads it at the start of the next run in the same
conversation. See [Keep the REPL across runs](https://pydantic.dev/docs/ai/harness/code-mode/#keep-the-repl-across-runs) in
the Pydantic AI docs, and [Keep an agent's work across conversation turns](conversations.md) for how this works.

## Verify it worked

Run `python agent.py`, then open the [Live view](../guides/web-ui/live.md). You should see the agent run's **trace**
(the full journey of one request, made of nested spans). Inside it, find the `run_code` tool call. It contains a
`run code` span with the script the model wrote, and a span for each tool the script called.

!!! warning "Scripts and tool results pass through and are recorded in Logfire"
    The scripts, your tools' arguments and results, and the final result are sent to Logfire's servers to run. With
    tracing on, Logfire also records them in your project, after its standard
    [scrubbing](../how-to-guides/scrubbing.md).

## Troubleshooting

- **`UserError` that mentions `monty_sandbox_url`**: set either `monty_pool_factory` or `monty_sandbox_url`, not both.
- **`LogfireConfigError: Agent sandboxes require a Logfire API key`**: the run started without an API key. Set
  `LOGFIRE_API_KEY`, or pass `api_key` to `logfire.configure()`.
- **The model retries after a "crashed worker" error on long scripts**: increase `request_timeout`, as above.
- **The model calls a tool directly instead of from `run_code`**: Code Mode keeps some tools outside the sandbox, such as
  tools that load lazily. See [Selective tool sandboxing](https://pydantic.dev/docs/ai/harness/code-mode/#selective-tool-sandboxing).

## Next steps

- [Work with large tool results](large-results.md): tools that return more rows than the model should read.
- [What sandbox code can do](limits.md): the parts of Python that scripts can use.
- [Code Mode](https://pydantic.dev/docs/ai/harness/code-mode/): every Code Mode option, in the Pydantic AI docs.
