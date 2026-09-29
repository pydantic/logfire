---
title: "Query limits"
description: "The limits Logfire applies to queries for each plan, what happens when your organization reaches a limit, and what to do."
---

# Query limits

Logfire limits the number of queries that each organization can run, and how much work those queries can do. These limits stop one organization from making queries slow for other organizations.

These limits apply to Logfire Cloud in the [US and EU regions](data-regions.md).

## Query sources

A query source is the place that a query comes from. Each query source has its own limits.

| Query source | The queries it includes |
| --- | --- |
| Web UI | Queries from the Logfire web application. For example, [Explore](../guides/web-ui/explore.md), [dashboards](../guides/web-ui/dashboards.md), and the [Live view](../guides/web-ui/live.md). |
| Read tokens | Queries that use a [read token](../how-to-guides/query-api.md). For example, the query API, the Python query clients, and the DB API. |
| MCP | Queries from the [Logfire MCP server](../how-to-guides/mcp-server.md). |
| Public API | Requests to the [public API](advanced/use-api-keys.md) with an API key. |

When one query source reaches a limit, the other query sources continue to work. For example, if your scripts use all of the read token budget, you can still use the web UI.

## Limits for each plan

Each query source has two types of limit:

- **Running queries:** the maximum number of queries that run at the same time. When a query source has this number of running queries, Logfire puts new queries in a queue. A queued query waits until one of the running queries is complete.
- **Daily budgets:** the maximum query work in 24 hours. For read tokens, a daily budget counts the number of queries, the compute time, and the data scanned. For the web UI, it counts the compute time. For MCP, it counts the number of queries. Compute time is the time that Logfire's servers use to run your queries. Data scanned is the amount of stored data that Logfire reads to find the results.

This table gives the limit level for each plan. The levels are Low, Standard, and High. A higher level lets you run more queries and do more query work.

| Query source and limit | Personal | Team | Growth | Enterprise |
| --- | --- | --- | --- | --- |
| Web UI: running queries | Low | Standard | High | High |
| Web UI: daily budget | Low | Standard | No daily budget | No daily budget |
| Read tokens: running queries | Low | Standard | High | High |
| Read tokens: daily budget | Low | Standard | High | High |
| MCP: running queries | Low | Standard | High | High |
| MCP: daily budget | Low | Standard | High | High |
| Public API: running queries | Low | Standard | High | High |

The public API has no daily budget.

"No daily budget" does not mean that there is no limit. Logfire can still refuse queries to protect the service for all organizations.

### How a daily budget refills

A daily budget does not reset at a fixed time. It refills a small amount at a time, all through the day. After 24 hours with no queries, the budget is full again.

Each hour, a budget gets back 1/24 of its full size. You can use all of the budget in a short time. Then you can send more queries when part of the budget has refilled.

### Queries that have no daily budget

Daily budgets do not apply to these queries:

- Queries that check your [alerts](../guides/web-ui/alerts.md). Alert limits apply only when you create or change an alert.
- The Live view stream of new records.
- [Public trace](../guides/web-ui/public-traces.md) links.
- Scheduled work that Logfire does for your organization.

## What happens when you reach a limit

When Logfire refuses a query, it sends back the HTTP status `429 Too Many Requests` and a `Retry-After` header. The `Retry-After` value is the number of seconds to wait before you send the query again.

**Too many running queries:** Logfire puts the query in the queue. If the query waits in the queue for too long, Logfire refuses it. The `Retry-After` value is a few seconds.

**A daily budget is used:** Logfire refuses all new queries from that query source. The error message tells you which query source reached its budget, and when you can send queries again. The `Retry-After` value gives the same time in seconds. The other query sources are not affected.

Logfire measures query use approximately once each minute. Thus a query source can go a small amount over its budget before Logfire starts to refuse queries.

## What to do when Logfire refuses a query

### Wait, then try again

Wait for the number of seconds in the `Retry-After` header, then send the query again. Do not send the query again immediately. Each query that you send before the budget refills is refused too.

If a script sends queries, make it read `Retry-After` and wait before it tries again. For example:

```python skip-run="true" skip-reason="external-connection"
import time

import httpx

url = 'https://logfire-us.pydantic.dev/v1/query'
headers = {'Authorization': 'Bearer <your read token>'}
params = {'sql': 'SELECT count(*) FROM records'}

response = httpx.get(url, params=params, headers=headers)
if response.status_code == 429:
    time.sleep(int(response.headers.get('Retry-After', '60')))
    response = httpx.get(url, params=params, headers=headers)
```

### Make each query do less work

A query that reads less data uses less compute time and less of the data scanned budget. To read less data:

- **Use a shorter time range.** With the query API, set `min_timestamp` and `max_timestamp` to the smallest range that you need.
- **Filter the rows.** Add a `WHERE` clause on columns such as `service_name`, `deployment_environment`, or `span_name`.
- **Select only the columns that you need.** Do not use `SELECT *`.
- **Use `LIMIT`** when you need only some of the rows.

### Send fewer queries

- **Combine queries.** One query with `GROUP BY` can replace many queries that each get one value.
- **Keep the results.** If you need the same result again, keep it in your script. Do not send the same query again.
- **Send queries less frequently.** If a script checks for new data, do not check more frequently than the data changes. For example, if you need a value each hour, send the query one time each hour, not each minute.
- **Divide large jobs across the day.** A daily budget refills all through the day. A job that sends many queries at one time uses the budget quickly and must then wait.

### Read only new data

If a script reads your data again and again, do not read the same time range each time. Read only the records that Logfire stored after the last read.

Each record has a `created_at` column. `created_at` is the time when Logfire stored the record. This is not the same as `start_timestamp`, which is the time when your application started the span.

Logfire guarantees this: after `created_at` is more than 5 minutes in the past, no more records get that `created_at` value. Thus you can use `created_at` as a cursor:

1. Keep the upper bound of the last read. On the first read, choose a start time.
2. Set the new upper bound to 5 minutes before the current time.
3. Read the records with `created_at` after the last upper bound and not after the new upper bound.
4. Save the new upper bound for the next read.

For example:

```sql
SELECT *
FROM records
WHERE created_at > '2026-01-01T12:00:00Z'  -- the last upper bound
  AND created_at <= '2026-01-01T12:10:00Z' -- 5 minutes before the current time
```

With the query API, `min_timestamp` and `max_timestamp` filter on `start_timestamp`, not on `created_at`. Set `min_timestamp` early enough to include the records that you want, and do not set `max_timestamp`.

Each record is in exactly one read. Records do not appear in more than one read, and no record is missed. Records are available to a script 5 minutes after Logfire stores them.

### Get higher limits

- **Upgrade your plan.** Higher plans have higher limits. See [pricing](https://pydantic.dev/pricing).
- **Contact support** if you need higher limits than your plan gives.

## Next steps

- [Query API](../how-to-guides/query-api.md): read your data with a read token.
- [Logfire MCP server](../how-to-guides/mcp-server.md): let an AI agent read your data.
- [Ingest limits](limits.md): the limits on the data that you send to Logfire.
