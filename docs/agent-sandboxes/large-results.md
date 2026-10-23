---
title: "Work with large tool results without filling the context window"
description: "Let your agent reduce thousands of rows from several sources to a short answer in a sandbox, so the model reads only the answer."
---

# Work with large tool results without filling the context window

!!! info "Experimental"
    Agent Sandboxes is available to selected Logfire organizations. See [access and availability](index.md).

"Which recent deploys coincide with more exceptions?" To answer, an agent needs the error counts for every service over
several hours, the list of deploys, and a comparison of error rates before and after each deploy. As tool results, that
is hundreds of rows that the model must read and compare in its head. Every row takes space in the model's **context
window** (the text the model reads on each turn), costs **tokens** (the units models read and bill by), and gives the
model another chance to misread a number.

With Agent Sandboxes, the model writes a script that fetches the rows, compares them in Python, and returns only the
deploys with a higher proportion of exception-bearing spans. The rows stay in the [sandbox](index.md). The model reads one line.

This page uses an on-call agent as the example. The same pattern fits any agent whose tools return more data than the
model needs to read: account histories, search results, spreadsheets, or log lines.

## Before you start

- Follow [Run code from Python](python.md) to install `logfire[agent-sandboxes]` and set `LOGFIRE_API_KEY` to a key with
  permission to run code in agent sandboxes.
- Install the query client dependency with `pip install httpx`.
- To query your real data, create a **read token** (a credential that lets code query your project's data) in
  **Settings → Read tokens**. See [Query API](../how-to-guides/query-api.md).

!!! warning "Query results leave your application"
    Query results pass through Logfire's sandbox service. Default client instrumentation also records the rows in
    your project. Scrubbing applies to client telemetry, not the execution request or saved state.
    See [tracing controls](limits.md#control-client-tracing) before you send sensitive data.

## Give the agent the data sources as functions

The first function runs SQL against your Logfire project with the [query client](../how-to-guides/query-api.md). The
second returns recent deploys. Replace it with a call to your deploy system.

```python title="tools.py" skip-run="true" skip-reason="external-connection"
import os
from datetime import datetime, timedelta, timezone

from logfire.query_client import AsyncLogfireQueryClient


async def query_logfire(sql: str) -> list[dict]:
    """Run a SQL query against the Logfire project's last 24 hours of data and return the rows."""
    since = datetime.now(timezone.utc) - timedelta(hours=24)
    async with AsyncLogfireQueryClient(read_token=os.environ['LOGFIRE_READ_TOKEN']) as client:
        result = await client.query_json_rows(sql, min_timestamp=since)
    return result['rows']


async def list_deploys(since_hours: int) -> list[dict]:
    """List deploys from the last `since_hours` hours, oldest first."""
    now = datetime.now(timezone.utc)
    return [  # replace with a call to your deploy system
        {'service': 'checkout', 'version': 'v412', 'deployed_at': (now - timedelta(hours=4)).isoformat()},
        {'service': 'auth', 'version': 'v88', 'deployed_at': (now - timedelta(hours=3)).isoformat()},
        {'service': 'search', 'version': 'v1201', 'deployed_at': (now - timedelta(hours=1)).isoformat()},
    ]
```

The sandbox never sees `LOGFIRE_READ_TOKEN`. It can only call `query_logfire` and `list_deploys`, and both run in your
application.

## See the script your agent writes

A model asked "which recent deploys coincide with more exceptions?" can write a script like this one:

```python title="main.py" skip-run="true" skip-reason="external-connection"
import asyncio

from tools import list_deploys, query_logfire

import logfire

logfire.configure()

AGENT_CODE = '''
from datetime import datetime, timedelta

rows = await query_logfire("""
    SELECT service_name, time_bucket('5 minutes', start_timestamp) AS bucket,
           count(*) FILTER (WHERE is_exception) AS errors, count(*) AS spans
    FROM records
    WHERE start_timestamp > now() - interval '6 hours'
      AND span_type = 'span'
    GROUP BY service_name, bucket
""")
deploys = await list_deploys(since_hours=6)


def error_rate(service, start, end):
    window = [r for r in rows if r['service_name'] == service and start <= datetime.fromisoformat(r['bucket']) < end]
    spans = sum(r['spans'] for r in window)
    return sum(r['errors'] for r in window) / spans if spans else None


suspects = []
for d in deploys:
    at = datetime.fromisoformat(d['deployed_at'])
    before = error_rate(d['service'], at - timedelta(minutes=30), at)
    after = error_rate(d['service'], at, at + timedelta(minutes=30))
    if before is not None and after is not None and after > 2 * before and after > 0.005:
        suspects.append({**d, 'error_rate_before': round(before, 4), 'error_rate_after': round(after, 4)})
suspects
'''


async def main():
    async with logfire.agent_sandboxes() as pool:
        async with pool.checkout() as session:
            result = await session.feed_run(
                AGENT_CODE,
                external_lookup={'query_logfire': query_logfire, 'list_deploys': list_deploys},
            )
    print(result)


asyncio.run(main())
```

Set `LOGFIRE_READ_TOKEN` and run `python main.py`. The output depends on your data. In a project with four services
and a bad `auth` deploy, the query returns 288 rows, and the script prints one deploy:

```
[{'service': 'auth', 'version': 'v88', 'deployed_at': '2026-10-23T09:00:00+00:00', 'error_rate_before': 0.0015, 'error_rate_after': 0.0297}]
```

The model reads the summary instead of all 288 rows. This ratio counts exception-bearing spans, not failed requests.
A change after a deploy is a lead to investigate. It does not prove that the deploy caused the exceptions.

This example closes its session after the first answer. For a follow-up, keep the session open or save its ID and
restore it. See [Keep an agent's work across conversation turns](conversations.md).

We asked this question of a Pydantic AI agent with `gpt-5.4-mini`, three times with plain tool calls and three times
with [Agent Sandboxes through Code Mode](pydantic-ai.md). Both found the `auth` deploy every time. With plain tool
calls, the model read all 288 rows, and each run used about 34,600 input tokens. With Agent Sandboxes, each run used
about 7,400. These three-run results use fixed sample data. They do not predict production cost or accuracy.

In your application, the agent writes the script and your code runs it. See [Use Agent Sandboxes with Pydantic
AI](pydantic-ai.md) or [Add a code tool to any agent](any-framework.md).

## Why a script beats SQL alone here

The query does the part that SQL is good at: counting errors per service in five-minute buckets. The comparison needs
data that this query does not contain (the external deploy list). A script can join any number of sources,
and the model can change the comparison for each question without you adding a new tool.

When one query can answer the whole question, let the agent run that query as a plain tool call. A separate sandbox step may be unnecessary.

A sandbox session has a 20 MiB memory limit, including interpreter state and retained variables, so a script can work with a few thousand rows at a time, not millions. Let the
query aggregate first, as the five-minute buckets do here, and let the script compare and join.

## Verify it worked

Open the [Live view](../guides/web-ui/live.md). You should see a `run code` span with a child span for each of the two
tool calls. Open the `query_logfire` span to see the SQL the model wrote and the 288 rows it returned. You can see every
row the script used, even though the model never read them.

## Troubleshooting

- **`MontyRuntimeError: TimeoutError: feed time limit exceeded`**: each run in a hosted sandbox can use only a short
  amount of processing time. Time spent waiting for your tools does not count. Let the query do the heavy aggregation,
  and keep the script to comparing and filtering. See [What sandbox code can do](limits.md).
- **`KeyError` on a column name**: the script used a column the query did not select. The error message goes back to
  the model, which usually corrects the script on its next try.
- **`429 Too Many Requests` from `query_logfire`**: a daily query budget is exhausted, or a queued query waits too
  long. Wait before you retry and reduce query work. See [query limits](../reference/query-limits.md).

## Next steps

- [Answer questions that need dozens of tool calls](many-tool-calls.md): call tools in parallel from one script.
- [Keep an agent's work across conversation turns](conversations.md): keep the rows for follow-up questions.
- [Give an agent a whole API](typed-api.md): check the agent's code against your types before it runs.
