# PyMongo

The [OpenTelemetry Instrumentation PyMongo][opentelemetry-pymongo] package can be used to instrument [PyMongo][pymongo].

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
from opentelemetry.instrumentation.pymongo import PymongoInstrumentor

logfire.configure()
PymongoInstrumentor().instrument()

client = MongoClient()
db = client["database"]
collection = db["collection"]
collection.insert_one({"name": "MongoDB"})
collection.find_one()
```

---

You can read more about the PyMongo OpenTelemetry package [here][opentelemetry-pymongo].

[pymongo]: https://pymongo.readthedocs.io/en/stable/
[opentelemetry-pymongo]: https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/pymongo/pymongo.html
