---
title: "Work with large tool results without filling the context window"
description: "Let your agent reduce thousands of rows from several sources to a short answer in a sandbox, so the model reads only the answer."
---

# Work with large tool results without filling the context window

"Did one of today's deploys cause the new errors?" To answer, an agent needs the error counts for every service over
several hours, the list of deploys, and a comparison of error rates before and after each deploy. As tool results, that
is hundreds of rows that the model must read and compare in its head. Every row takes space in the model's **context
window** (the text the model reads on each turn), costs **tokens** (the units models read and bill by), and gives the
model another chance to misread a number.

With Agent Sandboxes, the model writes a script that fetches the rows, compares them in Python, and returns only the
deploys that look guilty. The rows stay in the [sandbox](index.md). The model reads one line.

This page uses an on-call agent as the example. The same pattern fits any agent whose tools return more data than the
model needs to read: account histories, search results, spreadsheets, or log lines.

## Before you start

- Follow [Run code from Python](python.md) to install `logfire[agent-sandboxes]` and set `LOGFIRE_API_KEY` to a key with
  the **Execute agent sandboxes** permission.
- To query your real data, create a **read token** (a credential that lets code query your project's data) in
  **Settings → Read tokens**. See [Query API](../how-to-guides/query-api.md).

## Give the agent the data sources as functions

The first function runs SQL against your Logfire project with the [query client](../how-to-guides/query-api.md). The
second returns recent deploys. Replace it with a call to your deploy system.

```python title="tools.py" skip-run="true" skip-reason="external-connection"
import os

from logfire.experimental.query_client import AsyncLogfireQueryClient


async def query_logfire(sql: str) -> list[dict]:
    """Run a SQL query against the Logfire project and return the rows."""
    async with AsyncLogfireQueryClient(read_token=os.environ['LOGFIRE_READ_TOKEN']) as client:
        result = await client.query_json_rows(sql)
    return result['rows']


async def list_deploys(since_hours: int) -> list[dict]:
    """List deploys from the last `since_hours` hours, oldest first."""
    return [  # replace with a call to your deploy system
        {'service': 'checkout', 'version': 'v412', 'deployed_at': '2026-10-23T08:00:00+00:00'},
        {'service': 'auth', 'version': 'v88', 'deployed_at': '2026-10-23T09:00:00+00:00'},
        {'service': 'search', 'version': 'v1201', 'deployed_at': '2026-10-23T10:30:00+00:00'},
    ]
```

The sandbox never sees `LOGFIRE_READ_TOKEN`. It can only call `query_logfire` and `list_deploys`, and both run in your
application.

## See the script your agent writes

A model asked "did one of today's deploys cause the new errors?" writes a script like this one:

```python title="main.py" skip-run="true" skip-reason="external-connection"
import asyncio

import logfire

from tools import list_deploys, query_logfire

logfire.configure()

AGENT_CODE = '''
from datetime import datetime, timedelta

rows = await query_logfire("""
    SELECT service_name, time_bucket('5 minutes', start_timestamp) AS bucket,
           count(*) FILTER (WHERE is_exception) AS errors, count(*) AS requests
    FROM records
    WHERE start_timestamp > now() - interval '6 hours'
    GROUP BY service_name, bucket
""")
deploys = await list_deploys(since_hours=6)


def error_rate(service, start, end):
    window = [r for r in rows if r['service_name'] == service and start <= datetime.fromisoformat(r['bucket']) < end]
    requests = sum(r['requests'] for r in window)
    return sum(r['errors'] for r in window) / requests if requests else 0.0


suspects = []
for d in deploys:
    at = datetime.fromisoformat(d['deployed_at'])
    before = error_rate(d['service'], at - timedelta(minutes=30), at)
    after = error_rate(d['service'], at, at + timedelta(minutes=30))
    if after > 2 * before and after > 0.005:
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

The model reads that line, not 288 rows. It can then ask a follow-up question in the same session, because `rows` and
`deploys` are still defined there. See [Keep an agent's work across conversation turns](conversations.md).

In your application, the agent writes the script and your code runs it. See [Use Agent Sandboxes with Pydantic
AI](pydantic-ai.md) or [Add a code tool to any agent](any-framework.md).

## Why a script beats SQL alone here

The query does the part that SQL is good at: counting errors per service in five-minute buckets. The comparison needs
data that is not in Logfire (the deploy list), so no single query can do it. A script can join any number of sources,
and the model can change the comparison for each question without you adding a new tool.

When one query can answer the whole question, let the agent run that query as a plain tool call. A sandbox adds nothing
there.

## Verify it worked

Open the [Live view](../guides/web-ui/live.md). You should see a `run code` span with a child span for each of the two
tool calls. Open the `query_logfire` span to see the SQL the model wrote and the 288 rows it returned. You can see every
row the script used, even though the model never read them.

!!! warning "Query results are recorded in your project"
    With tracing on (the default), Logfire records each tool call's arguments and result, including the rows your
    query returns, after its standard [scrubbing](../how-to-guides/scrubbing.md). If those rows hold data that must not
    be copied, see [What sandbox code can do](limits.md) for how to turn tracing off.

## Troubleshooting

- **`MontyRuntimeError: TimeoutError: feed time limit exceeded`**: each run in a hosted sandbox can use only a short
  amount of processing time. Time spent waiting for your tools does not count. Let the query do the heavy aggregation,
  and keep the script to comparing and filtering. See [What sandbox code can do](limits.md).
- **`KeyError` on a column name**: the script used a column the query did not select. The error message goes back to
  the model, which usually corrects the script on its next try.
- **`429 Too Many Requests` from `query_logfire`**: read tokens have [query limits](../reference/query-limits.md). Fewer,
  larger queries help.

## Next steps

- [Answer questions that need dozens of tool calls](many-tool-calls.md): call tools in parallel from one script.
- [Keep an agent's work across conversation turns](conversations.md): keep the rows for follow-up questions.
- [Give an agent a whole API](typed-api.md): check the agent's code against your types before it runs.
