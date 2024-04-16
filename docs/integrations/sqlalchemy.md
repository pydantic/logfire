# SQLAlchemy

The [OpenTelemetry Instrumentation SQLAlchemy][opentelemetry-sqlalchemy] package can be used to
instrument [SQLAlchemy][sqlalchemy].

## Installation

Install `logfire` with the `sqlalchemy` extra:

{{ install_logfire(extras=['sqlalchemy']) }}

## Usage

Let's see a minimal example below. You can run it with `python main.py`:

```py title="main.py"
import logfire
from sqlalchemy import create_engine
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

logfire.configure()

engine = create_engine("sqlite:///:memory:")
SQLAlchemyInstrumentor().instrument(engine=engine)
```

You can read more about the SQLAlchemy OpenTelemetry package [here][opentelemetry-sqlalchemy].

!!! tip
    If you use [SQLModel][sqlmodel], you can use the same `SQLAlchemyInstrumentor` to instrument it.

[opentelemetry-sqlalchemy]: https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/sqlalchemy/sqlalchemy.html
[sqlalchemy]: https://www.sqlalchemy.org/
[sqlmodel]: https://sqlmodel.tiangolo.com/
