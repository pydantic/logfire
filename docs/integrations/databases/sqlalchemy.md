---
integration: otel
---

The [`logfire.instrument_sqlalchemy()`][logfire.Logfire.instrument_sqlalchemy] method will create a span for every query executed by a [SQLAlchemy][sqlalchemy] engine.

## Installation

Install `logfire` with the `sqlalchemy` extra:

{{ install_logfire(extras=['sqlalchemy']) }}

## Usage

Let's see a minimal example below. You can run it with `python main.py`:

=== "Instrument a Single Engine"

    ```py title="main.py"
    from sqlalchemy import create_engine

    import logfire

    logfire.configure()

    engine = create_engine('sqlite:///:memory:')
    logfire.instrument_sqlalchemy(engine=engine)
    ```

=== "Instrument Multiple Engines"

    ```py title="main.py"
    from sqlalchemy import create_engine

    import logfire

    logfire.configure()

    engine_one = create_engine('sqlite:///:memory:')
    engine_two = create_engine('sqlite:///:memory:')
    logfire.instrument_sqlalchemy(engines=[engine_one, engine_two])
    ```

The keyword arguments of `logfire.instrument_sqlalchemy()` are passed to the `SQLAlchemyInstrumentor().instrument()` method of the OpenTelemetry SQLAlchemy Instrumentation package, read more about it [here][opentelemetry-sqlalchemy].

!!! warning
    It's best to use the `engine` or `engines` arguments. If no engine is specified, then `instrument_sqlalchemy` may
    only work if it's called before `sqlalchemy` is imported, in which case all engines are instrumented.

!!! tip
    If you use [SQLModel][sqlmodel], you can use the same `SQLAlchemyInstrumentor` to instrument it.

[opentelemetry-sqlalchemy]: https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/sqlalchemy/sqlalchemy.html
[sqlalchemy]: https://www.sqlalchemy.org/
[sqlmodel]: https://sqlmodel.tiangolo.com/
