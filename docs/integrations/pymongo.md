# PyMongo

The [`logfire.instrument_pymongo()`][logfire.Logfire.instrument_pymongo] method will create a span for every operation performed using your [PyMongo][pymongo] clients.

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

!!! info
    You can pass `capture_statement` to `logfire.instrument_redis()` to capture the Redis command.

    By default, it is set to `False` given that Redis commands can contain sensitive information.

The keyword arguments of `logfire.instrument_pymongo()` are passed to the `PymongoInstrumentor().instrument()` method of the OpenTelemetry pymongo Instrumentation package, read more about it [here][opentelemetry-pymongo].

[pymongo]: https://pymongo.readthedocs.io/en/stable/
[opentelemetry-pymongo]: https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/pymongo/pymongo.html
