---
title: "Instrument SQLAlchemy: see every database query your app runs"
description: "See every database query your app runs through SQLAlchemy (the SQL, how long it took, and which ones failed) as spans in Logfire."
integration: otel
---
# SQLAlchemy

See every database query your app runs through [SQLAlchemy](https://www.sqlalchemy.org/) in Logfire: the SQL statement, how long it took, and which ones failed. Each query becomes a **span** (one timed step, with a name and a duration), shown nested inside the request that triggered it, so you can spot the slow or failing query behind a slow endpoint.

## What you'll capture

- One span per query, with its duration and status
- The SQL statement that ran, and the database it ran against
- Failed queries, with the error

## Before you start

You'll need a Logfire project and its **write token** (the key your app uses to send data). Create one and copy it from **Project → Settings → Write tokens**. See [Getting Started](../../index.md).

## Installation

Install `logfire` with the `sqlalchemy` extra:

{{ install_logfire(extras=['sqlalchemy']) }}

## Usage

Call `logfire.configure()`, then `logfire.instrument_sqlalchemy()` with your engine. A minimal example you can run with `python main.py`:

=== "One engine"

    ```py title="main.py" skip-run="true" skip-reason="global-state" hl_lines="8"
    from sqlalchemy import create_engine

    import logfire

    logfire.configure()

    engine = create_engine('sqlite:///:memory:')
    logfire.instrument_sqlalchemy(engine=engine)
    ```

=== "Multiple engines"

    ```py title="main.py" skip-run="true" skip-reason="global-state" hl_lines="9"
    from sqlalchemy import create_engine

    import logfire

    logfire.configure()

    engine_one = create_engine('sqlite:///:memory:')
    engine_two = create_engine('sqlite:///:memory:')
    logfire.instrument_sqlalchemy(engines=[engine_one, engine_two])
    ```

!!! warning "Pass your engine explicitly"
    Prefer the `engine` or `engines` argument. If you don't specify one, `instrument_sqlalchemy()` only works when it's called *before* `sqlalchemy` is imported, in which case it instruments every engine.

!!! tip "Using SQLModel?"
    [SQLModel](https://sqlmodel.tiangolo.com/) is built on SQLAlchemy, so the same call instruments it.

## Verify it worked

Run a query through your engine, then open the [Live view](../../guides/web-ui/live.md). Within a few seconds you'll see a span for the query, with its duration and the SQL it ran, nested under the request span if you've also instrumented your [web framework](../web-frameworks/index.md).

<!-- TODO(app-verify): screenshot of a SQLAlchemy query span in the Live view, showing the SQL statement and duration -->

## Troubleshooting

Not seeing queries? Check that `logfire.configure()` ran before `instrument_sqlalchemy()`, that your write token is set, that you passed your `engine` (or `engines`), and that you called the instrument function exactly once.

## Advanced

The keyword arguments of `logfire.instrument_sqlalchemy()` are passed straight to the OpenTelemetry `SQLAlchemyInstrumentor().instrument()` method. See the [OpenTelemetry SQLAlchemy instrumentation][opentelemetry-sqlalchemy] docs for the full option list.

## Reference

- [`logfire.instrument_sqlalchemy()`][logfire.Logfire.instrument_sqlalchemy]: the Logfire API reference.
- [OpenTelemetry SQLAlchemy instrumentation][opentelemetry-sqlalchemy]: the underlying package.

[opentelemetry-sqlalchemy]: https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/sqlalchemy/sqlalchemy.html
