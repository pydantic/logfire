# [PyMongo][pymongo]

The [OpenTelemetry Instrumentation PyMongo][opentelemetry-pymongo] package can be used to instrument PyMongo.

## Installation

Install `logfire` with the `pymongo` extra:

{{ install_logfire(extras=['pymongo']) }}

## Usage

Let's see a minimal example below:

<!-- TODO(Marcelo): Create a secret gist with a docker-compose. -->

```py title="main.py"
import logfire
from pymongo import MongoClient
from opentelemetry.instrumentation.pymongo import PymongoInstrumentor

logfire.configure()
PymongoInstrumentor().instrument()

client = MongoClient()
db = client["test-database"]
collection = db["test-collection"]
collection.insert_one({"name": "MongoDB"})
collection.find_one()
```

You can read more about the PyMongo OpenTelemetry package [here][opentelemetry-pymongo].

[pymongo]: https://pymongo.readthedocs.io/en/stable/
[opentelemetry-pymongo]: https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/pymongo/pymongo.html
