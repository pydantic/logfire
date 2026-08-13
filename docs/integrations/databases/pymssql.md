---
title: "Instrument PyMSSQL: see every SQL Server query your app runs"
description: "See the SQL Server queries your app runs through PyMSSQL, how long they take, and which ones fail."
integration: otel
---
# PyMSSQL

See every query your app sends to Microsoft SQL Server through [PyMSSQL][pymssql] in Logfire. Each
query becomes a **span** (one unit of work with a name, a start, and a duration), so you can see the
SQL statement, how long it took, and which request triggered it.

{{ before_you_start() }}

## Installation

Install `logfire` with the `pymssql` extra:

{{ install_logfire(extras=['pymssql']) }}

## Usage

Call [`logfire.instrument_pymssql()`][logfire.Logfire.instrument_pymssql] after configuring Logfire
and before opening a connection:

```py title="main.py" hl_lines="6" skip-run="true" skip-reason="external-connection"
import pymssql

import logfire

logfire.configure()
logfire.instrument_pymssql()

with pymssql.connect(
    server='localhost',
    port='1433',
    user='sa',
    password='yourStrong(!)Password',
    database='master',
) as connection:
    with logfire.span('Read server version'), connection.cursor() as cursor:
        cursor.execute('SELECT @@VERSION')
        print(cursor.fetchone())
```

!!! warning "Avoid double instrumentation with SQLAlchemy"

    If SQLAlchemy opens your PyMSSQL connections, use
    [`logfire.instrument_sqlalchemy()`](sqlalchemy.md) instead. Instrumenting both SQLAlchemy and
    PyMSSQL records two spans for each query.

## Verify it worked

Run your program, then open your project in the [Logfire web app](https://logfire.pydantic.dev/) and
go to the **Live** view. You should see the `SELECT` span nested inside `Read server version`. Click
the query span to inspect its SQL statement and connection details.

## Troubleshooting

- **No query spans appear.** Call `logfire.configure()` and `logfire.instrument_pymssql()` before
  `pymssql.connect()`.
- **Every query appears twice.** Instrument either PyMSSQL or SQLAlchemy, not both.
- **The connection fails.** Check that SQL Server accepts connections at the configured server and
  port, and that the user can access the database.

## Reference

- API reference: [`logfire.instrument_pymssql()`][logfire.Logfire.instrument_pymssql]
- Underlying package: [OpenTelemetry PyMSSQL instrumentation][opentelemetry-pymssql]

[opentelemetry-pymssql]: https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/pymssql/pymssql.html
[pymssql]: https://pymssql.readthedocs.io/
