---
title: "Instrument SurrealDB: see database operations"
description: "Add Logfire to the SurrealDB Python client and see database operations alongside the code that triggered them."
integration: logfire
---
# SurrealDB

See the database work your app sends to [SurrealDB][surrealdb] alongside the code that triggered it.
Logfire records most operations as a **span** (one unit of work: a single operation, with a name, a
start, and a duration). Related spans appear in the same **trace** (the full journey of one request,
made of nested spans), so you can find slow and failed operations in context.

The integration supports the connections returned by both the synchronous `Surreal()` and
asynchronous `AsyncSurreal()` factory functions.

## What you'll capture

- Each non-generator operation as a span, with its duration and any errors
- Generator-based operations such as `subscribe_live` as a **log** (a timestamped record of a single
  event, with no duration); errors raised while iterating are not captured
- The operation name, such as `surrealdb create`, `surrealdb query`, or `surrealdb select`
- Relevant method arguments, with Logfire's standard sensitive-data scrubbing applied

{{ before_you_start() }}

## Install Logfire and SurrealDB

Install `logfire`:

{{ install_logfire() }}

Install the separately distributed `surrealdb` package:

```bash
pip install surrealdb
```

## Record every operation

Call [`logfire.instrument_surrealdb()`][logfire.Logfire.instrument_surrealdb] before creating a
connection. With no arguments, it records operations from every SurrealDB connection in the process.

This example uses an in-memory database, so you do not need to start a SurrealDB server:

```python title="main.py" hl_lines="6"
import asyncio

from surrealdb import AsyncSurreal

import logfire

logfire.configure()
logfire.instrument_surrealdb()


async def main():
    async with AsyncSurreal(url='mem://') as db:
        await db.use('test', 'test')
        await db.create('person', {'name': 'Alice', 'age': 30})
        people = await db.select('person')
        logfire.info('Found {count} people', count=len(people))


if __name__ == '__main__':
    asyncio.run(main())
```

Run it with `python main.py`.

## Verify it worked

Open the [Live view](../../guides/web-ui/live.md). Within a few seconds, you should see spans named
`surrealdb use`, `surrealdb create`, and `surrealdb select`. Click a span to see its duration and
arguments.

## Choose specific connections

The no-argument call is the common choice. Use the following options when you need to limit which
connections Logfire records.

### Record one connection

Pass a connection instance to record operations from only that connection. Call
`logfire.instrument_surrealdb(db)` before using it:

```python
from surrealdb import Surreal

import logfire

logfire.configure()

db = Surreal(url='mem://')
logfire.instrument_surrealdb(db)

with db:
    db.use('test', 'test')
    db.create('person', {'name': 'Alice'})
```

### Record one connection class

Pass a concrete connection class to record every instance of that class. For example, this records
asynchronous WebSocket connections without recording HTTP or embedded connections:

```python
from surrealdb import AsyncWsSurrealConnection

import logfire

logfire.configure()
logfire.instrument_surrealdb(AsyncWsSurrealConnection)
```

`Surreal` and `AsyncSurreal` are factory functions, not connection classes. Do not pass either
factory to `logfire.instrument_surrealdb()`.

## Troubleshoot missing spans

- **Importing `surrealdb` fails:** install the client separately with `pip install surrealdb`.
- **No SurrealDB spans appear:** call `logfire.configure()` before
  `logfire.instrument_surrealdb()`, then instrument before the first database operation.
- **Only some connections appear:** call `logfire.instrument_surrealdb()` with no argument to record
  all connection classes. If you pass an instance or class, Logfire records only that target.
- **No data appears in Logfire:** check that your write token is set. Run
  `logfire projects use <your-project>` locally, or set the `LOGFIRE_TOKEN` environment variable in
  production. See [Getting Started](../../index.md).

[surrealdb]: https://surrealdb.com/
