---
title: "Instrument SQLite: see every query your app runs"
description: "Add a few lines to your sqlite3 code and see every query in Logfire: the statement, how long it took, and which ones failed."
integration: otel
---
# SQLite3

See every query your app runs through Python's built-in [`sqlite3`][sqlite3] module (the statement,
how long it took, and which ones failed) as a **span** (one unit of work with a name, a start, and a
duration) in Logfire. Related spans link together into a **trace** (the full journey of one request),
so a slow query shows up right next to the code that triggered it.

## What you'll capture

- Each query as a span, with its duration and any errors
- The SQL statement that ran

## Before you start

You'll need a Logfire project and its **write token**: the credential your app uses to send data to
Logfire. Create a project and copy its token from **Project → Settings → Write tokens** in the
Logfire web app. New to Logfire? Start with [Getting Started](../../index.md), which walks through
creating a project and linking your machine.

## Installation

Install `logfire` with the `sqlite3` extra:

{{ install_logfire(extras=['sqlite3']) }}

## Usage

Add two lines to your app: `logfire.configure()` to connect to your project, and
[`logfire.instrument_sqlite3()`][logfire.Logfire.instrument_sqlite3] to record every query. The
example below uses an in-memory database so you can run it as-is.

```py title="main.py" hl_lines="5-6" skip-run="true" skip-reason="global-state"
import sqlite3

import logfire

logfire.configure()
logfire.instrument_sqlite3()

with sqlite3.connect(':memory:') as connection:
    cursor = connection.cursor()

    cursor.execute('CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT)')
    cursor.execute("INSERT INTO users (name) VALUES ('Alice')")

    cursor.execute('SELECT * FROM users')
    print(cursor.fetchall())
    #> [(1, 'Alice')]

connection.close()
```

Run it with `python main.py`.

## Verify it worked

Run your program, then open your project in the
[Logfire web app](https://logfire.pydantic.dev/) and go to the **Live** view. Within a few seconds you
should see a span for each query the script ran. Click one to see the SQL statement and how long it
took.

<!-- TODO(app-verify): screenshot of the query spans in the Live view, showing the SQL statement and duration -->

## Troubleshooting

Not seeing your queries in Logfire? Check these first:

- **`logfire.configure()` runs before `logfire.instrument_sqlite3()`.** Configure the connection
  first, then instrument.
- **You call `instrument_sqlite3()` exactly once.**
- **You run queries through a cursor, not the connection.** The `execute` method on
  [`sqlite3.Connection`][sqlite3.Connection] is *not* instrumented; use the `execute` method on a
  [`Cursor`][sqlite3.Cursor] instead (see the note below).
- **Your write token is set.** In local development, run `logfire projects use <your-project>`; in
  production, set the `LOGFIRE_TOKEN` environment variable. See [Getting Started](../../index.md).

## Advanced

### Instrumenting a single connection

Instead of the whole module, you can instrument just one connection:

```py title="main.py" hl_lines="5 8" skip-run="true" skip-reason="global-state"
import sqlite3

import logfire

logfire.configure()

with sqlite3.connect(':memory:') as connection:
    connection = logfire.instrument_sqlite3(connection)
    cursor = connection.cursor()

    cursor.execute('CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT)')
    cursor.execute("INSERT INTO users (name) VALUES ('Alice')")

    cursor.execute('SELECT * FROM users')
    print(cursor.fetchall())
    #> [(1, 'Alice')]

connection.close()
```

!!! warning "Run queries through a cursor, not the connection"
    The [`execute`][sqlite3.Connection.execute] method from [`Connection`][sqlite3.Connection] is not
    instrumented, so those queries won't appear in Logfire.

    Use the [`execute`][sqlite3.Cursor.execute] method from the [`Cursor`][sqlite3.Cursor] object
    instead.

    See [opentelemetry-python-contrib#3082](https://github.com/open-telemetry/opentelemetry-python-contrib/issues/3082)
    for more information.

## Reference

- API reference: [`logfire.instrument_sqlite3()`][logfire.Logfire.instrument_sqlite3]
- Underlying OpenTelemetry package: [SQLite3 instrumentation][opentelemetry-sqlite3]

[opentelemetry-sqlite3]: https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/sqlite3/sqlite3.html
[sqlite3]: https://docs.python.org/3/library/sqlite3.html
