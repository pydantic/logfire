---
integration: logfire
---

## Introduction

Logfire supports instrumenting [PydanticAI](https://ai.pydantic.dev/).

```python hl_lines="5"
import logfire
from pydantic_ai import Agent, RunContext

logfire.configure()
Agent.instrument_all()
```

Note:

* You will need to provide your `LOGFIRE_TOKEN` and LLM-appropriate API key environment variables.

With that you get:

* A span around all LLM calls your agent makes which records duration and captures any exceptions that might occur
* Human-readable display of the conversation with the agent
* Details of the request/response, including the number of tokens used

You can also instrument **specific** agents with this approach:

```python hl_lines="15"
import logfire
from pydantic_ai import Agent, RunContext

logfire.configure()


roulette_agent = Agent(
    'openai:gpt-4o',
    deps_type=int,
    result_type=bool,
    system_prompt=(
        'Use the `roulette_wheel` function to see if the '
        'customer has won based on the number they provide.'
    ),
    instrument=True
)


@roulette_agent.tool
async def roulette_wheel(ctx: RunContext[int], square: int) -> str:
    """check if the square is a winner"""
    return 'winner' if square == ctx.deps else 'loser'


# Run the agent
success_number = 18
result = roulette_agent.run_sync('Put my money on square eighteen', deps=success_number)
print(result.data)
#> True

result = roulette_agent.run_sync('I bet five is the winner', deps=success_number)
print(result.data)
#> False
```

The above example displays like this in Logfire:

<figure markdown="span">
  ![Logfire PydanticAI Instrumentation](../../images/integrations/pydantic-ai/pydanticai-instrumentation-screenshot.
png)
  <figcaption>PydanticAI instrumented and displayed in Logfire</figcaption>
</figure>

You can use PydanticAI with a [large variety of LLMs](https://ai.pydantic.dev/api/models/base/#pydantic_ai.models.KnownModelName), the example
just happens to show `gpt-4o`.

For more information, see the [PydanticAI docs on instrumenting](https://ai.pydantic.dev/#instrumentation-with-pydantic-logfire) with Logfire.
