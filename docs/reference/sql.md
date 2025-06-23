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
