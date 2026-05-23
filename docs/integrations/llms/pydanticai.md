---
title: Logfire Pydantic AI Integration
description: "Get deep visibility into your Pydantic AI agents. Logfire tracing captures every tool call, retry, and complex agent step for reliable, structured debugging."
integration: logfire
---
**Pydantic Logfire** supports instrumenting [Pydantic AI](https://pydantic.dev/docs/ai/overview/) with the
[`logfire.instrument_pydantic_ai()`][logfire.Logfire.instrument_pydantic_ai] method:

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

The above example displays like this in **Logfire**:

/// public-trace | https://logfire-eu.pydantic.dev/public-trace/953848ba-11a8-4368-a21b-c9bda69a7f58?spanId=9026260034697d53
    title: 'Logfire instrumentation of the agent run'
///

You can use Pydantic AI with a [large variety of LLMs][pydantic_ai.models.KnownModelName], the example
just happens to show `gpt-5-mini`.

You can also instrument a specific agent with `logfire.instrument_pydantic_ai(agent)`.

For more information, see the [`logfire.instrument_pydantic_ai()`][logfire.Logfire.instrument_pydantic_ai]
reference or the [Pydantic AI docs on instrumenting](https://pydantic.dev/docs/ai/integrations/logfire/) with **Logfire**.

## Keep model pricing up to date

Pydantic AI uses [`genai-prices`](https://github.com/pydantic/genai-prices) to populate the
`operation.cost` span attribute. The model price catalogue is shipped as a snapshot inside the
package, mirroring the official provider pricing pages (e.g.
[Google Gemini API pricing](https://ai.google.dev/gemini-api/docs/pricing) and
[OpenAI API pricing](https://openai.com/api/pricing/)), so newly released models
(e.g. `gemini-3.5-flash`, `gpt-5.1`, …) only get a cost calculation once a new version of
`genai-prices` is released and pulled in.

To always pick up new prices without waiting for a release, pass `update_genai_prices=True`
to `logfire.configure()`. A daemon thread will refresh the catalogue from upstream every hour
in the background:

```python skip-run="true" skip-reason="external-connection"
import logfire

logfire.configure(update_genai_prices=True)
logfire.instrument_pydantic_ai()
```

The same can be enabled via the `LOGFIRE_UPDATE_GENAI_PRICES=1` environment variable.

The thread needs outbound HTTP access to `raw.githubusercontent.com` and is a no-op (with a
one-shot warning) when `genai-prices` is not installed in the environment.
