---
integration: otel
---

The [`logfire.instrument_pymongo()`][logfire.Logfire.instrument_pymongo] method will create a span for every operation performed using your [PyMongo][pymongo] clients.

!!! success "Also works with Motor... 🚗"
    This integration also works with [`motor`](https://motor.readthedocs.io/en/stable/), the asynchronous driver for MongoDB.

## Installation

Install `logfire` with the `pymongo` extra:

{{ install_logfire(extras=['pymongo']) }}

## Usage

The following example demonstrates how to use **Logfire** with PyMongo.

### Run Mongo on Docker (Optional)

If you already have a MongoDB instance running, you can skip this step.
Otherwise, you can start MongoDB using Docker with the following command:

```bash
docker run --name mongo -p 27017:27017 -d mongo:latest
```

### Run the Python script

The following script connects to a MongoDB database, inserts a document, and queries it:

=== "Sync"

    ```py
    import logfire
    from pymongo import MongoClient

    logfire.configure()
    logfire.instrument_pymongo()

    client = MongoClient()
    db = client["database"]
    collection = db["collection"]
    collection.insert_one({"name": "MongoDB"})
    collection.find_one()
    ```

=== "Async"

    ```py
    import asyncio
    import logfire
    from motor.motor_asyncio import AsyncIOMotorClient

    logfire.configure()
    logfire.instrument_pymongo()

    async def main():
        client = AsyncIOMotorClient()
        db = client["database"]
        collection = db["collection"]
        await collection.insert_one({"name": "MongoDB"})
        await collection.find_one()

    asyncio.run(main())
    ```

!!! info
    You can pass `capture_statement=True` to `logfire.instrument_pymongo()` to capture the queries.

    By default, it is set to `False` to avoid capturing sensitive information.

The keyword arguments of `logfire.instrument_pymongo()` are passed to the `PymongoInstrumentor().instrument()` method of the OpenTelemetry pymongo Instrumentation package, read more about it [here][opentelemetry-pymongo].

## API Reference

::: logfire.Logfire.instrument_pymongo
    options:
        heading_level: 4
        show_source: false
        show_root_doc_entry: true
        show_root_heading: true
        show_root_full_path: false

::: logfire.integrations.pymongo.RequestHook
    options:
        heading_level: 4
        show_root_heading: true
        show_root_full_path: false
        show_source: false
        filters: []

::: logfire.integrations.pymongo.ResponseHook
    options:
        heading_level: 4
        show_root_heading: true
        show_root_full_path: false
        show_source: false
        filters: []

::: logfire.integrations.pymongo.FailedHook
    options:
        heading_level: 4
        show_root_heading: true
        show_root_full_path: false
        show_source: false
        filters: []

[pymongo]: https://pymongo.readthedocs.io/en/stable/
[opentelemetry-pymongo]: https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/pymongo/pymongo.html
