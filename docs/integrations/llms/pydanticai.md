---
integration: logfire
---

**Logfire** supports instrumenting [PydanticAI](https://ai.pydantic.dev/) with the
[`logfire.instrument_pydantic_ai()`][logfire.Logfire.instrument_pydantic_ai] method:

```python hl_lines="5"
import logfire
from pydantic_ai import Agent, RunContext

logfire.configure()
logfire.instrument_pydantic_ai()

roulette_agent = Agent(
    'openai:gpt-4o',
    deps_type=int,
    result_type=bool,
    system_prompt=(
        'Use the `roulette_wheel` function to see if the '
        'customer has won based on the number they provide.'
    ),
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

The above example displays like this in **Logfire**:

![Logfire PydanticAI Instrumentation](../../images/integrations/pydantic-ai/pydanticai-instrumentation-screenshot.
png)

You can use PydanticAI with a [large variety of LLMs](https://ai.pydantic.dev/api/models/base/#pydantic_ai.models.KnownModelName), the example
just happens to show `gpt-4o`.

You can also instrument a specific agent with `logfire.instrument_pydantic_ai(agent)`.

For more information, see the [`logfire.instrument_pydantic_ai()`][logfire.Logfire.instrument_pydantic_ai]
reference or the [PydanticAI docs on instrumenting](https://ai.pydantic.dev/logfire/) with **Logfire**.
