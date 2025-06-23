# SQL

## Syntax

**Logfire** lets you query your data using SQL. The underlying database is Apache DataFusion, so the primary reference for the SQL syntax can be found in their [SQL Language Reference](https://datafusion.apache.org/user-guide/sql/index.html). However it's generally meant to match [PostgreSQL syntax](https://www.postgresql.org/docs/current/queries.html) which is easier to look up. We also extend it in various ways, particularly with [JSON functions and operators](https://github.com/datafusion-contrib/datafusion-functions-json) such as `->>`.

## Tables

Data is stored in two main tables: `records` and `metrics`.

`records` is the table you'll usually care about and is what you'll see in the Live View. Each row in `records` is a span or log (essentially a span with no duration). A _trace_ is a collection of spans that share the same `trace_id`, structured as a tree.

`metrics` contains pre-aggregated numerical data which is usually more efficient to query than `records` for certain use cases. There's currently no dedicated UI for metrics, but you can query it directly using SQL in the Explore view, Dashboards, Alerts, or the API, just like you would with `records`.

Technically `records` is a subset, the full table is called `records_full` which includes additional rows called pending spans, but you can ignore that for most use cases.

## `records` columns

### Basic

To demonstrate some commonly used columns, if you run this script:

```python
import logfire

logfire.configure()

logfire.warn('beware: {thing}', thing='bad', _tags=['a tag'])
```

You will see this in the Live view:

![Basic columns example in the live view](../images/sql-reference/basic-columns-live.png)

Here's an example of querying in the Explore view:

![Basic columns example in the explore view](../images/sql-reference/basic-columns-explore.png)

#### `span_name`

This is a string label which is typically shared by similar records. Clicking the `span_name` bubble in the details panel of the Live view will give you a few options to filter by that span name, which is a good way to find other records like this one. It should be _low cardinality_, meaning there shouldn't be too many unique values.

When using methods from the **Logfire** SDK, this will usually be the template without any arguments filled in, e.g. above it's `'beware: {thing}'`.

In HTTP server request spans, this is usually the HTTP method and route, e.g. `'GET /users/{id}'`. Note that it doesn't use the actual path (e.g. `/users/123`).

In database query spans, this is usually just the operation, e.g. `'SELECT'`, `'INSERT'`, or `'UPDATE'`.

See the docs on [messages and span names](../guides/onboarding-checklist/add-manual-tracing.md#messages-and-span-names) and the [OpenTelemetry spec](https://opentelemetry.io/docs/specs/otel/trace/api/#span) for more details.

#### `message`

This is a human-readable description of the record. It's the text in each line of the list of records in the Live view.

Typically this is similar to the `span_name` but with any arguments filled in, e.g. above it's `'beware: bad'`.

In HTTP server request spans, this is usually the HTTP method and route with the actual path filled in, e.g. `'GET /users/123'`.

In database query spans from the Python **Logfire** SDK, this is usually a _summary_ of the SQL query. This can be useful for finding and grouping records with similar but slightly different queries.

It's usually faster and more correct to use `span_name` in queries. `message` is primarily for human readability and is more likely to change over time. But if you want to query it, you probably want to use the `LIKE` (or `ILIKE` for case-insensitive) SQL operator, e.g. `WHERE message LIKE '%bad%'` to find all records where `message` contains the substring `bad`.

OpenTelemetry doesn't have a native 'message' concept. To set a value for the `message` column when using other OpenTelemetry SDKs, set the attribute `logfire.msg`. This will not be kept in the `attributes` column.

#### `attributes`

This is a JSON object containing arbitrary additional structured data about the record. It can vary widely between records and even be empty.

You can query it using the `->>` operator, e.g. above `attributes->>'thing' = 'bad'` (note the single quotes, `"thing"` or `"bad"` would look for SQL columns with those names and fail) would match our record because of the `thing='bad'` argument in the `logfire.warn()` call. For nested JSON, you can chain multiple `->>` operators, e.g. `attributes->>'nested'->>'key'`. You can also use `->` which is mostly interchangeable, but if you get weird errors about types, try using `->>` instead.

See the [manual tracing docs on attributes](../guides/onboarding-checklist/add-manual-tracing.md#attributes) for more information about setting attributes in the **Logfire** SDK.

Note that arguments passed directly to the **Logfire** SDK methods are shown under 'Arguments' in the Live view details panel, but they are still stored in the same `attributes` column.

#### `tags`

This is an optional array of strings that can be used to group records together.

Each tag is displayed as a colored bubble in the Live view after the message.

To find records with the same tag, use the `array_has` function, e.g. `array_has(tags, 'a tag')` in the above example.

To set a tag in the Python **Logfire** SDK, pass a list of strings to the `_tags` argument in the SDK methods. Note the leading underscore. Alternatively, [`logfire.with_tags('a tag')`][logfire.Logfire.with_tags] will return a new `Logfire` instance with all the usual methods, where `'a tag'` will be automatically included in the tags of all method calls.

OpenTelemetry doesn't have a native 'tags' concept. To set a value for the `tags` column when using other OpenTelemetry SDKs, set the attribute `logfire.tags`. This will not be kept in the `attributes` column.

#### `level`

This represents the severity level (aka the 'log level') of the record.

It's stored in the database as a small integer so that it supports operators like `>=` and `<`, but we provide some SQL magic to allow you to use the string names in comparisons. For example, `level = 'warn'` will match the example record above, even though the actual stored value is `13`. A common useful query is `level > 'info'` to find all 'notable' records like warnings and errors.

The level is most commonly set by using the appropriate method in the **Logfire** SDK, e.g. `logfire.warn(...)` or `logfire.error(...)`, but there are [several other ways](../guides/onboarding-checklist/add-manual-tracing.md#log-levels).

The default level for spans is `info`. If a span ends with an unhandled exception, the level is usually set to `error`. One special case is that FastAPI/Starlette `HTTPException`s with a 4xx status code (client errors) are set to `warn`.

You can convert level names to numbers using the `level_num` SQL function, e.g. `level_num('warn')` returns `13`.

You can also use the `level_name` SQL function to convert numbers to names, e.g. `SELECT level_name(level), ...` to see a human-readable level in the Explore view.

The numerical values are based on the [OpenTelemetry spec](https://opentelemetry.io/docs/specs/otel/logs/data-model/#field-severitynumber). Some common values: `info` is `9`, `warn` is `13`, and `error` is `17`.

OpenTelemetry _logs_ have a native severity level, but _spans_ do not. Spans with a status code of `ERROR` will have a level of `error`, otherwise the level is set to `info`. To set a custom value for the `level` column when using other OpenTelemetry SDKs, set the attribute `logfire.level_num`. This will not be kept in the `attributes` column.

### Span tree

#### `trace_id`

This is a unique identifier for the trace that this span/log belongs to.

A trace is a collection of one or more records that share the same `trace_id`, structured as a tree. It typically represents one high level operation such as an HTTP server request or a batch job.

If you query individual records in the explore view, dashboard tables, or alerts, we recommend including `trace_id` in the `SELECT` clause. The values will become clickable links in the UI that will take you to the Live view filtered by that trace, making it easy to explore a record in context. For alerts sent as slack messages, note that this doesn't apply to the slack message itself, but the title of the slack message will link to the alert run results in the UI, and the table there will have clickable `trace_id` links.

Technically the trace ID is a 128-bit (16 byte) integer, but in the database it's represented as a 32-character hexadecimal string. For example, the following code:

```python
from opentelemetry.trace import format_trace_id

import logfire

logfire.configure()

with logfire.span('foo') as span:
    trace_id = span.get_span_context().trace_id
    print(trace_id)
    print(format_trace_id(trace_id))
```

will print something like:

```
2116451560797328055476200846428238844
01979d1e4e4325335569dba4459473fc
```

The second line is what you'll see in the database and UI.

Most OpenTelemetry SDKs generate trace IDs that are completely random. However, the Python **Logfire** SDK generates trace IDs where the first few characters are based on the current time. This means that if you want to quickly check at a glance if two records are part of the same trace, it's better to look at the _last_ characters.

### Timestamps

#### `start_timestamp`

The UTC time when the span/log was first created/started.

This is the time shown on the left side of the list of records in the Live view.

All views in the UI have some time range dropdown that filters on this column, so you usually don't have to. For example, in the Live view the default is set to 'Last 5 minutes'. But if you wanted to do this manually in SQL, you could use a `WHERE` clause like `start_timestamp >= now() - interval '5 minutes'`.

In dashboard queries, a time series chart querying `records` should have `time_bucket($resolution, start_timestamp)` in the `SELECT` clause, which will be used as the x-axis. `$resolution` is a variable that will be replaced with the time resolution of the dashboard, e.g. `1 minute`. This variable doesn't exist outside of dashboards, so if you want to copy a query from a dashboard to the Explore view, tick 'Show rendered query' first. This will fill in the variable with the actual value, e.g. `time_bucket('1 minute', start_timestamp)`.

!!! warning
    Prefer this column over `created_at`, which is an internal timestamp representing when the record was created in the database.

!!! warning
    The `metrics` table also has a `start_timestamp` column, but you should usually use `recorded_timestamp` instead, which doesn't exist in the `records` table.

#### `end_timestamp`

The UTC time when the span/log was completed/ended.

For logs, this is the same as `start_timestamp` because logs don't have a duration.

#### `duration`

The time in seconds between `start_timestamp` and `end_timestamp`.

For example, `duration > 2` will match all spans that took longer than 2 seconds to complete.

For logs, this is always `null`. Otherwise it's equivalent to `EXTRACT(EPOCH FROM (end_timestamp - start_timestamp))`.
