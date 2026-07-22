---
title: "Debug a slow tool call"
description: "Your agent takes seconds to answer. Is that the model, or something it called? Trace a Pydantic AI agent in Logfire, prove a tool, not the LLM, is the bottleneck, and find the slow query inside it."
---
# Debug a slow tool call

Your agent takes a few seconds to answer, and the instinct is to blame the model. Usually it isn't. An
agent's time is mostly spent in the **tools** it calls (a database lookup, a search, an API request),
not in the language model itself. From the outside the two are indistinguishable: all you see is "the
agent is slow." A trace tells them apart.

This walkthrough takes a [Pydantic AI](https://ai.pydantic.dev/) agent that's slow to respond and uses
Logfire to show, in one trace, that the model calls are fast and a single **tool call** is eating the
time, then drills into that tool to find the query behind it.

**Who this is for:** AI engineers building agents who want to know *where* an agent's latency actually
goes, instead of guessing it's "the LLM."

**Time:** about 15 minutes.

Two terms, once: a **span** is one unit of work with a name and a duration; a **trace** is the tree of
nested spans for one request. The whole trick here is that when the agent-run span *contains* the
model-call spans and the tool-call span, you can read their durations side by side and see which one is
slow.

## Prerequisites

- **A Logfire project and its write token.** Create a project and copy its token from
  **Project → Settings → Write tokens** in the [Logfire web app](https://logfire.pydantic.dev/). New to
  Logfire? See [Getting Started](../index.md).
- **A Google Gemini API key**, from [Google AI Studio](https://aistudio.google.com/apikey), set as
  `GEMINI_API_KEY`. The agent uses `google:gemini-flash-lite-latest`; any
  [model Pydantic AI supports](https://ai.pydantic.dev/models/) works: swap the model string and set
  that provider's key.
- **A PostgreSQL database** for the tool to query. A throwaway one with Docker:

    ```bash
    docker run --rm --name postgres \
        -e POSTGRES_USER=user -e POSTGRES_PASSWORD=secret -e POSTGRES_DB=database \
        -p 5432:5432 -d postgres
    ```

    Then seed a big table with **no index on `user_id`**. The size is what makes the query genuinely
    slow later (`psql postgres://user:secret@localhost:5432/database`):

    ```sql
    CREATE TABLE order_items (id serial PRIMARY KEY, user_id integer, product text, price numeric);
    INSERT INTO order_items (user_id, product, price)
    SELECT mod(i, 5), 'product-' || i, mod(i, 100) FROM generate_series(1, 15000000) i;
    ```

- **Python packages**: Pydantic AI, the Psycopg 3 driver, and Logfire's instrumentation for both:

    ```bash
    pip install "logfire[pydantic-ai,psycopg]" "pydantic-ai-slim[google]" "psycopg[binary]"
    ```

Set your write token and model key so the app can send traces and call the model:

```bash
export LOGFIRE_TOKEN=<your write token from Project → Settings → Write tokens>
export GEMINI_API_KEY=<your key from aistudio.google.com/apikey>
```

## 1. Build an agent with a tool that hits the database

Here's a small shopping-assistant agent with one tool. The tool answers "what does this customer spend
the most on?" with a `GROUP BY` query over the `order_items` table. Two instrumentation calls do the
work: `instrument_pydantic_ai()` records every agent run, model call, and tool call; `instrument_psycopg()`
records every SQL query as a span nested inside whatever called it.

```python title="agent.py" skip-run="true" skip-reason="external-connection"
import psycopg
from pydantic_ai import Agent, RunContext

import logfire

logfire.configure()
logfire.instrument_pydantic_ai()  # every agent run, model call, and tool call becomes a span
logfire.instrument_psycopg()  # every SQL query becomes a span, nested inside the tool that ran it

DSN = 'dbname=database user=user password=secret host=localhost port=5432'  # database connection string

agent = Agent(
    'google:gemini-flash-lite-latest',
    system_prompt='You are a shopping assistant. Use the `top_products` tool to answer what a customer spends most on.',
)


@agent.tool
async def top_products(ctx: RunContext[None], user_id: int) -> str:
    """Return the customer's highest-spend products."""
    # Async DB access inside an async tool, so the slow query doesn't block the event loop.
    async with await psycopg.AsyncConnection.connect(DSN) as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                'SELECT product, sum(price) AS spend FROM order_items '
                'WHERE user_id = %s GROUP BY product ORDER BY spend DESC LIMIT 5',
                (user_id,),
            )
            rows = await cur.fetchall()
    return ', '.join(f'{product} (${spend})' for product, spend in rows)


if __name__ == '__main__':
    result = agent.run_sync('What does customer 3 spend the most on?')
    print(result.output)
```

Run it (`python agent.py`). It answers in a few seconds: slow enough to be annoying, not obvious why.

## 2. The agent is slow: model or tool?

Open the [Live view](../guides/web-ui/live.md) and click the agent run to expand its trace. The top
`invoke_agent` span is the whole request; nested under it are the model calls and the tool call, each
with its own duration:

| Span                          | Duration | What it is                        |
| ----------------------------- | -------- | --------------------------------- |
| `invoke_agent agent`          | ~3.5 s   | the whole agent run               |
| `chat gemini-flash-lite-latest` | ~0.5 s | the model deciding to call the tool |
| `execute_tool top_products`   | **~2.3 s** | **your tool running**           |
| `chat gemini-flash-lite-latest` | ~0.7 s | the model writing the final answer |

There's the answer you can't get from the outside: **the model calls are fast (~0.5–0.7 s each); the
`top_products` tool took ~2.3 s.** "The agent is slow" was really "the `top_products` tool is slow, and
the LLM is fine." (Your exact seconds vary by hardware and data size, but the *shape*, a tool
dominating the model calls, is the point.)

This is the trap the trace saves you from: spending an afternoon tuning prompts or switching models to
shave latency that was never in the model.

## 3. Look inside the tool

Click the `execute_tool top_products` span to expand it. Nested inside is a single **SQL query span**
(`SELECT product, sum(price) … GROUP BY product …`) taking ~2.26 s, almost the entire tool call. So the
tool is slow for one concrete reason: that query.

This is the payoff of instrumenting both layers. Without the query span you'd know only that the tool
was slow; with it, you can see it's the `GROUP BY` aggregation over `order_items`, and click the span to
read its full SQL and timing.

One nuance worth knowing, because it's the opposite of the [slow endpoint](debug-a-slow-endpoint.md)
case: **an index on `user_id` barely helps here.** The cost isn't finding customer 3's rows: it's
aggregating millions of them. The real fix for a tool like this is to stop computing it live on every
agent call: precompute the "top products" table, cache the result, or narrow the data first. The
trace's job was to point you at *that* decision (the slow tool, then the slow query inside it) in
seconds instead of guesswork.

## What you've got now

- **A latency you can attribute.** "The agent is slow" became "the `top_products` tool is slow, not the
  model," and then "it's this `GROUP BY` query", each step read straight off one trace.
- **The general lesson.** Agent latency usually lives in tools and retrieval, not the model. Instrument
  the tools, and a slow agent stops being a mystery.

## Troubleshooting

- **Auth errors?** Set both `LOGFIRE_TOKEN` and `GEMINI_API_KEY`.
- **The SQL span isn't nested under the tool span?** `instrument_psycopg()` must run before the query, and the query must happen inside the tool (the async `AsyncConnection` in the example).
- **Postgres connection fails?** Confirm the throwaway container is running and the `DSN` host and port match it.

## What's next

- [Instrument and evaluate an agent](evaluate-an-agent.md): the full loop of building, tracing, and
  scoring the same kind of agent.
- [Debug a slow endpoint](debug-a-slow-endpoint.md): when the slow query *is* fixable with an index,
  and how to confirm the pattern across all your traffic in Explore.
- [AI observability](../ai-observability.md): everything Logfire captures from an agent, and why seeing
  the whole stack (model *and* tools) matters.
