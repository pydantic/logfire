---
title: "Instrument PyMongo: see every MongoDB operation your app runs"
description: "Add a few lines to your PyMongo code and see every MongoDB operation in Logfire: the command, how long it took, and which ones failed."
integration: otel
---
# PyMongo

See every operation your app runs against MongoDB through [PyMongo][pymongo] (the command, how long
it took, and which ones failed) as a **span** (one unit of work with a name, a start, and a duration)
in Logfire. Related spans link together into a **trace** (the full journey of one request), so a slow
lookup shows up right next to the code that triggered it.

!!! success "Also works with Motor"
    This integration also works with [`motor`](https://motor.readthedocs.io/en/stable/), the
    asynchronous driver for MongoDB.

## What you'll capture

- Each operation (insert, find, update, and so on) as a span, with its duration and any errors
- The collection and database the operation ran against
- Optionally, the command itself (off by default; see below)

## Before you start

You'll need a Logfire project and its **write token**: the credential your app uses to send data to
Logfire. Create a project and copy its token from **Project → Settings → Write tokens** in the
Logfire web app. New to Logfire? Start with [Getting Started](../../index.md), which walks through
creating a project and linking your machine.

## Installation

Install `logfire` with the `pymongo` extra:

{{ install_logfire(extras=['pymongo']) }}

## Usage

Add two lines to your app: `logfire.configure()` to connect to your project, and
[`logfire.instrument_pymongo()`][logfire.Logfire.instrument_pymongo] to record every operation.

The example below connects to a local MongoDB instance. If you don't have one running, you can start
one with Docker:

```bash
docker run --name mongo -p 127.0.0.1:27017:27017 -d mongo:latest
```

=== "Sync"

    ```py title="main.py" hl_lines="6" skip-run="true" skip-reason="external-connection"
    from pymongo import MongoClient

    import logfire

    logfire.configure()
    logfire.instrument_pymongo()

    client = MongoClient()
    db = client['database']
    collection = db['collection']
    collection.insert_one({'name': 'MongoDB'})
    collection.find_one()
    ```

=== "Async"

    ```py title="main.py" hl_lines="8" skip-run="true" skip-reason="external-connection"
    import asyncio

    from motor.motor_asyncio import AsyncIOMotorClient

    import logfire

    logfire.configure()
    logfire.instrument_pymongo()


    async def main():
        client = AsyncIOMotorClient()
        db = client['database']
        collection = db['collection']
        await collection.insert_one({'name': 'MongoDB'})
        await collection.find_one()


    asyncio.run(main())
    ```

Run it with `python main.py`.

## Verify it worked

Run your program, then open your project in the
[Logfire web app](https://logfire.pydantic.dev/) and go to the **Live** view. Within a few seconds you
should see a span for each operation the script ran. Click one to see the collection and how long it
took.

<!-- TODO(app-verify): screenshot of the MongoDB operation spans in the Live view, showing the collection and duration -->

## Troubleshooting

Not seeing your operations in Logfire? Check these first:

- **`logfire.configure()` runs before `logfire.instrument_pymongo()`.** Configure the connection
  first, then instrument.
- **You call `instrument_pymongo()` exactly once.**
- **Your write token is set.** In local development, run `logfire projects use <your-project>`; in
  production, set the `LOGFIRE_TOKEN` environment variable. See [Getting Started](../../index.md).
- **You actually ran an operation.** Spans appear only after a command executes.

## Advanced

### Capturing the command

By default, the command sent to MongoDB isn't recorded, since it can contain sensitive data. To
include it, pass `capture_statement=True`:

```py skip-run="true" skip-reason="external-connection"
import logfire

logfire.configure()
logfire.instrument_pymongo(capture_statement=True)
```

Turning this on sends the command (including any values in it) to Logfire, so avoid it if your queries
carry secrets or personally identifiable information (PII).

### Passing options to the OpenTelemetry instrumentor

[`logfire.instrument_pymongo()`][logfire.Logfire.instrument_pymongo] accepts additional keyword
arguments and passes them to the OpenTelemetry PyMongo instrumentation. See
[their documentation][opentelemetry-pymongo] for the full list.

## Reference

- Underlying OpenTelemetry package: [PyMongo instrumentation][opentelemetry-pymongo]

::: logfire.Logfire.instrument_pymongo
    options:
        heading_level: 4
        show_source: false
        show_root_doc_entry: true
        show_root_heading: true
        show_root_full_path: false

[pymongo]: https://pymongo.readthedocs.io/en/stable/
[opentelemetry-pymongo]: https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/pymongo/pymongo.html
