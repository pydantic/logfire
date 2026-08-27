---
title: "Instrument asyncpg: see every PostgreSQL query your app runs"
description: "Add a few lines to your asyncpg code and see every PostgreSQL query in Logfire: the statement, how long it took, and which ones failed."
integration: otel
---
# asyncpg

See every query your app sends to PostgreSQL through [asyncpg][asyncpg] (the statement, how long it
took, and which ones failed) as a **span** (one unit of work with a name, a start, and a duration) in
Logfire. Related spans link together into a **trace** (the full journey of one request), so a slow
query shows up right next to the code that triggered it.

## What you'll capture

- Each query as a span, with its duration and any errors
- The SQL statement that ran
- Which database the query went to

{{ before_you_start() }}

## Installation

Install `logfire` with the `asyncpg` extra:

{{ install_logfire(extras=['asyncpg']) }}

## Usage

Add two lines to your app: `logfire.configure()` to connect to your project, and
[`logfire.instrument_asyncpg()`][logfire.Logfire.instrument_asyncpg] to record every query.

The example below connects to a local PostgreSQL database. If you don't have one running, you can
start one with Docker:

```bash
docker run --name postgres \
    -e POSTGRES_USER=user \
    -e POSTGRES_PASSWORD=secret \
    -e POSTGRES_DB=database \
    -p 5432:5432 \
    -d postgres
```

This gives you a database you can reach at `postgres://user:secret@127.0.0.1:5432/database`.

```py title="main.py" hl_lines="8" skip-run="true" skip-reason="external-connection"
import asyncio

import asyncpg

import logfire

logfire.configure()
logfire.instrument_asyncpg()


async def main():
    connection: asyncpg.Connection = await asyncpg.connect(
        user='user', password='secret', database='database', host='127.0.0.1', port=5432
    )

    with logfire.span('Create table and insert data'):
        await connection.execute('CREATE TABLE IF NOT EXISTS test (id serial PRIMARY KEY, num integer, data varchar);')

        # Insert some data
        await connection.execute('INSERT INTO test (num, data) VALUES ($1, $2)', 100, 'abc')
        await connection.execute('INSERT INTO test (num, data) VALUES ($1, $2)', 200, 'def')

        # Query the data
        for record in await connection.fetch('SELECT * FROM test'):
            logfire.info('Retrieved {record=}', record=record)


asyncio.run(main())
```

Run it with `python main.py`.

## Verify it worked

Run your program, then open your project in the
[Logfire web app](https://logfire.pydantic.dev/) and go to the **Live** view. Within a few seconds you
should see a span for each query the script ran. Click one to see the SQL statement and how long it
took.

## Troubleshooting

Not seeing your queries in Logfire? Check these first:

- **`logfire.configure()` runs before `logfire.instrument_asyncpg()`.** Configure the connection
  first, then instrument.
- **You call `instrument_asyncpg()` exactly once.**
- **Your write token is set.** In local development, run `logfire projects use <your-project>`; in
  production, set the `LOGFIRE_TOKEN` environment variable. See [Getting Started](../../index.md).
- **You actually ran a query.** Spans appear only after a statement executes.

## Advanced

### Capturing query parameters

By default, the values you pass into queries aren't recorded, since they can contain sensitive data.
To include them, pass `capture_parameters=True`:

```py skip-run="true" skip-reason="external-connection"
import logfire

logfire.configure()
logfire.instrument_asyncpg(capture_parameters=True)
```

Turning this on sends the parameter values to Logfire, so avoid it if your queries carry secrets or
personally identifiable information (PII).

## Reference

- API reference: [`logfire.instrument_asyncpg()`][logfire.Logfire.instrument_asyncpg]
- Underlying OpenTelemetry package: [asyncpg instrumentation][opentelemetry-asyncpg]

[opentelemetry-asyncpg]: https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/asyncpg/asyncpg.html
[asyncpg]: https://magicstack.github.io/asyncpg/
