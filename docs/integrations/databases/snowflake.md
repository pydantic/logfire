---
title: "See Snowflake queries in Logfire"
description: "Add Logfire to the Snowflake Python client and see queries alongside the code that triggered them."
integration: logfire
---
# Snowflake

See the queries your app sends to [Snowflake][snowflake] alongside the code that triggered them.
Logfire records each query as a **span** (one unit of work: a single operation, with a name, a
start, and a duration). Related spans appear in the same **trace** (the full journey of one
request, made of nested spans), so you can find slow and failed queries in context.

**Instrumenting** Snowflake means adding the Logfire integration so it can see what your database
code is doing. The integration wraps the [Snowflake Connector for Python][snowflake-connector],
the client library that `snowflake-snowpark-python` and most other Snowflake tools also run their
queries through, so queries issued via Snowpark's `DataFrame` API get spans too.

## What you'll capture

- Each call to `connect()` as a span, with the target account, warehouse, database, schema, and
  role. Connection secrets (password, token, private key, etc.) are never captured.
- Each call to `execute()`/`executemany()` as a span, with the SQL text, row count, and Snowflake's
  own query ID (`sfqid`), with Logfire's standard **scrubbing**
  (automatically finding and hiding sensitive values in your telemetry, on your machine, before
  anything is sent) applied.

## What this integration does not capture

Snowflake's **compute cost** for a query (credits consumed, bytes scanned, warehouse queuing)
is not available at query time; Snowflake only exposes it minutes later through account-usage
views. To bring that data into Logfire, run the [OpenTelemetry Collector][otel-collector-overview]
(a separate program that sits between your apps and Logfire, gathering telemetry and forwarding
it) with its [`snowflakereceiver`][snowflakereceiver], and use the `sfqid` attribute this
integration records to match a query span to its later cost data.

{{ before_you_start() }}

## Install Logfire and the Snowflake connector

Install `logfire`:

{{ install_logfire() }}

Install the separately distributed `snowflake-connector-python` package:

```bash
pip install snowflake-connector-python
```

## Record every query

Call [`logfire.instrument_snowflake()`][logfire.Logfire.instrument_snowflake] before connecting.
With no arguments, it records queries from every connection in the process, including ones made
later.

```python title="main.py" hl_lines="6" skip-run="true" skip-reason="external-connection"
import snowflake.connector

import logfire

logfire.configure()
logfire.instrument_snowflake()

conn = snowflake.connector.connect(
    account='<account>',
    user='<user>',
    password='<password>',
    warehouse='<warehouse>',
    database='<database>',
    schema='<schema>',
)
cursor = conn.cursor()
cursor.execute('select current_version()')
```

Run it with `python main.py`.

### Capture query parameters

Query parameters may contain sensitive data. Logfire does not capture them by default. To include
them in spans, pass `capture_parameters=True` the first time you instrument a module or connection:

```python
import logfire

logfire.instrument_snowflake(capture_parameters=True)
```

Logfire's standard scrubbing still applies, but it may not identify every sensitive value. When you
instrument the same target more than once, the first call determines whether parameters are
captured.

## Verify it worked

Open the [Live view](../../guides/web-ui/live.md). Within a few seconds, you should see spans
named `snowflake connect` and `snowflake execute`. Click a span to see its duration and
attributes, including `sfqid` and `rowcount`.

## Record one connection

Pass a connection instance to record queries from only that connection. Call
`logfire.instrument_snowflake(conn)` after connecting:

```python skip-run="true" skip-reason="external-connection"
import snowflake.connector

import logfire

logfire.configure()

conn = snowflake.connector.connect(account='<account>', user='<user>', password='<password>')
logfire.instrument_snowflake(conn)

cursor = conn.cursor()
cursor.execute('select current_version()')
```

## Troubleshoot missing spans

- **Importing `snowflake.connector` fails:** install the client separately with
  `pip install snowflake-connector-python`.
- **No spans appear:** call `logfire.configure()` first. For module-wide instrumentation, call
  `logfire.instrument_snowflake()` before connecting. For one connection, connect first, then call
  `logfire.instrument_snowflake(conn)`.
- **No data appears in Logfire:** check that your write token is set. Run
  `logfire projects use <your-project>` locally, or set the `LOGFIRE_TOKEN` environment variable in
  production. See [Getting Started](../../index.md).

[snowflake]: https://www.snowflake.com/
[snowflake-connector]: https://docs.snowflake.com/en/developer-guide/python-connector/python-connector
[snowflakereceiver]: https://github.com/open-telemetry/opentelemetry-collector-contrib/blob/main/receiver/snowflakereceiver/documentation.md
[otel-collector-overview]: ../../how-to-guides/otel-collector/otel-collector-overview.md
