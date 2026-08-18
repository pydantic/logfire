---
title: "Logfire SurrealDB Integration & Setup Guide"
description: "Step-by-step guide for instrumenting SurrealDB connections with Logfire using the logfire.instrument_surrealdb() function."
---
# SurrealDB

The [`logfire.instrument_surrealdb()`][logfire.Logfire.instrument_surrealdb] function instruments [SurrealDB][surrealdb] connections, creating a span for each database operation.

Both **synchronous** (`SyncSurreal`) and **asynchronous** (`AsyncSurreal`) connection types are supported.

## Installation

Install `logfire` with the `surrealdb` extra:

{{ install_logfire(extras=['surrealdb']) }}

## Usage

### Instrument all connections (default)

Call `logfire.instrument_surrealdb()` before creating any connections to automatically instrument all SurrealDB connection instances:

```python skip-run="true" skip-reason="external-connection"
from surrealdb import AsyncSurreal

import logfire

logfire.configure()
logfire.instrument_surrealdb()


async def main():
    async with AsyncSurreal(url='ws://localhost:8000') as db:
        await db.signin({'username': 'root', 'password': 'root'})
        await db.use('test', 'test')

        # Each of these calls will create a span
        await db.create('person', {'name': 'Alice', 'age': 30})
        people = await db.select('person')
        logfire.info('Found {count} people', count=len(people))
```

### Instrument a single connection

Pass a specific connection instance to instrument only that connection:

```python skip-run="true" skip-reason="external-connection"
from surrealdb import SyncSurreal

import logfire

logfire.configure()

db = SyncSurreal(url='ws://localhost:8000')
logfire.instrument_surrealdb(db)

db.connect()
db.signin({'username': 'root', 'password': 'root'})
db.use('test', 'test')

result = db.query('SELECT * FROM person WHERE age > $age', {'age': 18})
logfire.info('Query returned {count} results', count=len(result))
db.close()
```

### Instrument a connection class

Pass a connection class to instrument all instances of that class:

```python
from surrealdb import AsyncSurreal

import logfire

logfire.configure()
logfire.instrument_surrealdb(AsyncSurreal)
```

[surrealdb]: https://surrealdb.com/
