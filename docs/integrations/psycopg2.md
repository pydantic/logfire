# [Psycopg2][psycopg2]

The [OpenTelemetry Instrumentation Psycopg2][opentelemetry-psycopg2] package can be used to instrument Psycopg2.

## Installation

Install `logfire` with the `psycopg2` extra:

{{ install_logfire(extras=['psycopg2']) }}

## Usage

```py
import psycopg2
from opentelemetry.instrumentation.psycopg2 import Psycopg2Instrumentor


Psycopg2Instrumentor().instrument()

cnx = psycopg2.connect(database='Database')
```

You can read more about the Psycopg2 OpenTelemetry package [here][opentelemetry-psycopg2].

[opentelemetry-psycopg2]: https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/psycopg2/psycopg2.html
[psycopg2]: https://www.psycopg.org/
