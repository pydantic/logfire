# [SQLAlchemy][sqlalchemy]

The [OpenTelemetry Instrumentation SQLAlchemy][opentelemetry-sqlalchemy] package can be used to instrument SQLAlchemy.

## Installation

Install `logfire` with the `sqlalchemy` extra:

{{ install_logfire(extras=['sqlalchemy']) }}

## Usage

```py
from sqlalchemy import create_engine

from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

engine = create_engine("sqlite:///:memory:")
SQLAlchemyInstrumentor().instrument(engine=engine)
```

You can read more about the SQLAlchemy OpenTelemetry package [here][opentelemetry-sqlalchemy].

[opentelemetry-sqlalchemy]: https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/sqlalchemy/sqlalchemy.html
[sqlalchemy]: https://www.sqlalchemy.org/
