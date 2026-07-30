---
title: "Instrument Pydantic AI: trace every agent step"
description: "See what your Pydantic AI agents do in Logfire, with every model call, tool call, and retry captured as spans."
integration: logfire
---
# Pydantic AI

See what your [Pydantic AI](https://pydantic.dev/docs/ai/overview/) agents do: every model call, every tool they invoke, and every retry, as a **trace** (the full journey of one agent run, made of nested **spans**, where each span is one unit of work with a name, a start, and a duration) in Logfire.

## What you'll capture

- Each agent run as a trace, with the model it used and how long it took
- The full conversation with the model, rendered so you can read it like a transcript
- Every tool call the agent made, as a child span with its arguments and result
- Retries, including the failed attempt that triggered each one
- Token usage for each model call, and any errors raised along the way

{{ before_you_start() }}

Your agent runs call a model provider (OpenAI, Anthropic, and others) using your own API key, so each run costs money on that provider account.

## Installation

Install `logfire`:

{{ install_logfire() }}

This integration works with your existing Pydantic AI install; there's no extra to add. If you don't have it yet, `pip install pydantic-ai`.

## Usage

Add two lines to your app: `logfire.configure()` to connect to your project, and [`logfire.instrument_pydantic_ai()`][logfire.Logfire.instrument_pydantic_ai] to record every agent run.

```python hl_lines="7-8" skip-run="true" skip-reason="external-connection"
from __future__ import annotations

from pydantic_ai import Agent, RunContext

import logfire

logfire.configure()
logfire.instrument_pydantic_ai()

roulette_agent = Agent(
    'openai:gpt-5-mini',
    deps_type=int,
    output_type=bool,
    system_prompt=(
        'Use the `roulette_wheel` function to see if the customer has won based on the number they provide.'
    ),
)


@roulette_agent.tool
async def roulette_wheel(ctx: RunContext[int], square: int) -> str:
    """Check if the square is a winner."""
    return 'winner' if square == ctx.deps else 'loser'


# Run the agent
success_number = 18
result = roulette_agent.run_sync('Put my money on square eighteen', deps=success_number)
print(result.output)
#> True

result = roulette_agent.run_sync('I bet five is the winner', deps=success_number)
print(result.output)
#> False
```

You can use Pydantic AI with a [large variety of models][pydantic_ai.models.KnownModelName]; the example just happens to show `gpt-5-mini`.

## Verify it worked

Run your program, then open the [Live view](../../guides/web-ui/live.md). Within a few seconds you'll see a trace for the agent run. Click it to read the conversation, expand the `roulette_wheel` tool call, and see the token count and duration.

The example above displays like this in Logfire:

/// public-trace | https://logfire-eu.pydantic.dev/public-trace/953848ba-11a8-4368-a21b-c9bda69a7f58?spanId=9026260034697d53
    title: 'Logfire instrumentation of the agent run'
///

## Advanced

### Instrument a single agent

To instrument one agent rather than all of them, pass it to the call:

```python skip="true" skip-reason="incomplete"
logfire.instrument_pydantic_ai(roulette_agent)
```

## Troubleshooting

Not seeing data? Check that `logfire.configure()` ran before `instrument_pydantic_ai()`, that your write token is set, and that you called the instrument function exactly once.

## Reference

- API reference: [`logfire.instrument_pydantic_ai()`][logfire.Logfire.instrument_pydantic_ai]
- [Pydantic AI docs on instrumenting with Logfire](https://pydantic.dev/docs/ai/integrations/logfire/)
