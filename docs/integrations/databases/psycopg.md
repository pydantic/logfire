---
title: "Instrument Psycopg: see every PostgreSQL query your app runs"
description: "Add a few lines to your Psycopg code and see every PostgreSQL query in Logfire: the statement, how long it took, and which ones failed."
integration: otel
---
# Psycopg

See every query your app sends to PostgreSQL through [Psycopg][psycopg] (the statement, how long it
took, and which ones failed) as a **span** (one unit of work with a name, a start, and a duration) in
Logfire. Related spans link together into a **trace** (the full journey of one request), so a slow
query shows up right next to the code that triggered it.

This works with both the `psycopg` (Psycopg 3) and `psycopg2` packages.

## What you'll capture

- Each query as a span, with its duration and any errors
- The SQL statement that ran
- Which database the query went to

{{ before_you_start() }}

## Installation

Install `logfire` with the `psycopg` extra:

{{ install_logfire(extras=['psycopg']) }}

Or, if you use `psycopg2`, install the `psycopg2` extra instead:

{{ install_logfire(extras=['psycopg2']) }}

## Usage

Add two lines to your app: `logfire.configure()` to connect to your project, and
[`logfire.instrument_psycopg()`][logfire.Logfire.instrument_psycopg] to record every query.

The example below connects to a local PostgreSQL database. If you don't have one running, you can
start one with Docker:

```bash
docker run --rm --name postgres \
    -e POSTGRES_USER=user \
    -e POSTGRES_PASSWORD=secret \
    -e POSTGRES_DB=database \
    -p 5432:5432 \
    -d postgres
```

This gives you a database you can reach at `postgres://user:secret@127.0.0.1:5432/database`.

```py title="main.py" hl_lines="5-6" skip-run="true" skip-reason="external-connection"
import psycopg

import logfire

logfire.configure()
logfire.instrument_psycopg()  # instrument whichever of psycopg/psycopg2 is installed

connection = psycopg.connect('dbname=database user=user password=secret host=127.0.0.1 port=5432')

with logfire.span('Create table and insert data'), connection.cursor() as cursor:
    cursor.execute('CREATE TABLE IF NOT EXISTS test (id serial PRIMARY KEY, num integer, data varchar);')

    # Insert some data
    cursor.execute('INSERT INTO test (num, data) VALUES (%s, %s)', (100, 'abc'))
    cursor.execute('INSERT INTO test (num, data) VALUES (%s, %s)', (200, 'def'))

    # Query the data
    cursor.execute('SELECT * FROM test')
```

Run it with `python main.py`.

## Verify it worked

Run your program, then open your project in the
[Logfire web app](https://logfire.pydantic.dev/) and go to the **Live** view. Within a few seconds you
should see a span for each query the script ran. Click one to see the SQL statement and how long it
took.

## Troubleshooting

Not seeing your queries in Logfire? Check these first:

- **`logfire.configure()` runs before `logfire.instrument_psycopg()`.** Configure the connection
  first, then instrument.
- **You call `instrument_psycopg()` exactly once.** With no argument it instruments the whole module;
  pass a connection to instrument just that one.
- **Your write token is set.** In local development, run `logfire projects use <your-project>`; in
  production, set the `LOGFIRE_TOKEN` environment variable. See [Getting Started](../../index.md).
- **You actually ran a query.** Spans appear only after a statement executes.

## Advanced

### Choosing what to instrument

You can instrument the whole module, a single package by name, or one connection:

```py skip-run="true" skip-reason="external-connection"
import psycopg

import logfire

logfire.configure()

# Instrument the whole module:
logfire.instrument_psycopg(psycopg)
# or by name:
logfire.instrument_psycopg('psycopg')
# or instrument whichever modules (psycopg and/or psycopg2) are installed:
logfire.instrument_psycopg()

connection = psycopg.connect('dbname=database user=user password=secret host=127.0.0.1 port=5432')

# Or instrument just one connection:
logfire.instrument_psycopg(connection)
```

### Adding context with SQL Commenter

SQL Commenter appends a comment to the end of each query with extra context (for example, the driver
name and version). This can help tools that read your database's own query logs correlate them back to
your app. Turn it on with `enable_commenter=True`:

```python
import logfire

logfire.configure()
logfire.instrument_psycopg(enable_commenter=True)
```

This can only be used when instrumenting the whole module, not individual connections.

By default the SQL comments include values for these keys:

- `db_driver`
- `dbapi_threadsafety`
- `dbapi_level`
- `libpq_version`
- `driver_paramstyle`
- `opentelemetry_values`

You can exclude any of these by passing a dictionary of keys mapped to `False` in `commenter_options`:

```python
import logfire

logfire.configure()
logfire.instrument_psycopg(
    enable_commenter=True,
    commenter_options={'db_driver': False, 'dbapi_threadsafety': False},
)
```

### Passing options to the OpenTelemetry instrumentor

[`logfire.instrument_psycopg()`][logfire.Logfire.instrument_psycopg] accepts additional keyword
arguments and passes them to the OpenTelemetry Psycopg instrumentation. See the
[OpenTelemetry Psycopg][opentelemetry-psycopg] and
[OpenTelemetry Psycopg2][opentelemetry-psycopg2] documentation for the full list.

## Reference

- Underlying OpenTelemetry packages: [Psycopg][opentelemetry-psycopg] ·
  [Psycopg2][opentelemetry-psycopg2]

::: logfire.Logfire.instrument_psycopg
    options:
        heading_level: 4
        show_source: false
        show_root_doc_entry: true
        show_root_heading: true
        show_root_full_path: false

::: logfire.integrations.psycopg.CommenterOptions
    options:
        heading_level: 4
        show_root_heading: true
        show_source: false
        filters: []

[opentelemetry-psycopg]: https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/psycopg/psycopg.html
[opentelemetry-psycopg2]: https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/psycopg2/psycopg2.html
[psycopg]: https://www.psycopg.org/
