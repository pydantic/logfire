---
title: "Instrument MySQL: see every query your app runs"
description: "Add a few lines to your MySQL code and see every query in Logfire: the statement, how long it took, and which ones failed."
integration: otel
---
# MySQL

See every query your app sends to MySQL through the [MySQL Connector/Python][mysql-connector] driver
(the statement, how long it took, and which ones failed) as a **span** (one unit of work with a name,
a start, and a duration) in Logfire. Related spans link together into a **trace** (the full journey of
one request), so a slow query shows up right next to the code that triggered it.

## What you'll capture

- Each query as a span, with its duration and any errors
- The SQL statement that ran
- Which database the query went to

## Before you start

You'll need a Logfire project and its **write token**: the credential your app uses to send data to
Logfire. Create a project and copy its token from **Project → Settings → Write tokens** in the
Logfire web app. New to Logfire? Start with [Getting Started](../../index.md), which walks through
creating a project and linking your machine.

## Installation

Install `logfire` with the `mysql` extra:

{{ install_logfire(extras=['mysql']) }}

## Usage

Add two lines to your app: `logfire.configure()` to connect to your project, and
[`logfire.instrument_mysql()`][logfire.Logfire.instrument_mysql] to record every query.

The example below connects to a local MySQL database. If you don't have one running, you can start one
with Docker:

```bash
docker run --name mysql \
    -e MYSQL_ROOT_PASSWORD=secret \
    -e MYSQL_DATABASE=database \
    -e MYSQL_USER=user \
    -e MYSQL_PASSWORD=secret \
    -p 3306:3306 \
    -d mysql
```

This gives you a database you can reach at `mysql://user:secret@127.0.0.1:3306/database`.

```py title="main.py" hl_lines="6" skip-run="true" skip-reason="external-connection"
import mysql.connector

import logfire

logfire.configure()
logfire.instrument_mysql()

connection = mysql.connector.connect(
    host='localhost',
    user='user',
    password='secret',
    database='database',
    port=3306,
    use_pure=True,
)

with logfire.span('Create table and insert data'), connection.cursor() as cursor:
    cursor.execute(
        'CREATE TABLE IF NOT EXISTS test (id INT AUTO_INCREMENT PRIMARY KEY, num integer, data varchar(255));'
    )

    # Insert some data
    cursor.execute('INSERT INTO test (num, data) VALUES (%s, %s)', (100, 'abc'))
    cursor.execute('INSERT INTO test (num, data) VALUES (%s, %s)', (200, 'def'))

    # Query the data
    cursor.execute('SELECT * FROM test')
    results = cursor.fetchall()
    for row in results:
        print(row)
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

- **`logfire.configure()` runs before `logfire.instrument_mysql()`.** Configure the connection first,
  then instrument.
- **You call `instrument_mysql()` exactly once.** With no argument it instruments the whole module;
  pass a connection to instrument just that one.
- **Your write token is set.** In local development, run `logfire projects use <your-project>`; in
  production, set the `LOGFIRE_TOKEN` environment variable. See [Getting Started](../../index.md).
- **You actually ran a query.** Spans appear only after a statement executes.

## Advanced

### Instrumenting a single connection

Instead of the whole module, you can instrument just one connection:

```py skip-run="true" skip-reason="external-connection"
import mysql.connector

import logfire

logfire.configure()

connection = mysql.connector.connect(
    host='localhost', user='user', password='secret', database='database', port=3306, use_pure=True
)
connection = logfire.instrument_mysql(connection)
```

### Passing options to the OpenTelemetry instrumentor

[`logfire.instrument_mysql()`][logfire.Logfire.instrument_mysql] accepts additional keyword arguments
and passes them to the OpenTelemetry MySQL instrumentation. See
[their documentation][opentelemetry-mysql] for the full list.

## Reference

- API reference: [`logfire.instrument_mysql()`][logfire.Logfire.instrument_mysql]
- Underlying OpenTelemetry package: [MySQL instrumentation][opentelemetry-mysql]

[opentelemetry-mysql]: https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/mysql/mysql.html
[mysql]: https://www.mysql.com/
[mysql-connector]: https://dev.mysql.com/doc/connector-python/en/
