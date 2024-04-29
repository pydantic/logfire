# Psycopg

The [`logfire.instrument_psycopg()`][logfire.Logfire.instrument_psycopg] function can be used to instrument [Psycopg][psycopg] PostgreSQL driver with **Logfire**. It works with both the `psycopg2` and `psycopg` (i.e. Psycopg 3) packages.

See the documentation for the [OpenTelemetry Psycopg Instrumentation][opentelemetry-psycopg] or the [OpenTelemetry Psycopg2 Instrumentation][opentelemetry-psycopg2] package for more details.

## Installation

Install `logfire` with the `psycopg` extra:

{{ install_logfire(extras=['psycopg']) }}

Or with the `psycopg2` extra:

{{ install_logfire(extras=['psycopg2']) }}

## Usage

<!-- TODO: Make sure this works. -->

Let's see a minimal example below. You can run it with `python main.py`:

```py title="main.py"
import logfire
import psycopg

logfire.configure()

# To instrument the whole module:
logfire.instrument_psycopg(psycopg)
# or
logfire.instrument_psycopg('psycopg')
# or just instrument whichever modules (psycopg and/or psycopg2) are installed:
logfire.instrument_psycopg()

connection = psycopg.connect(database='database')
# Or instrument just the connection:
logfire.instrument_psycopg(connection)

cursor = connection.cursor()
cursor.execute("SELECT * FROM Table")

connection.close()
```

## SQL Commenter

To add SQL comments to the end of your queries to enrich your database logs with additional context, use the `enable_commenter` parameter:

```python
import logfire

logfire.instrument_psycopg(enable_commenter=True)
```

This can only be used when instrumenting the whole module, not individual connections.

By default the SQL comments will include values for the following keys:

- `db_driver`
- `dbapi_threadsafety`
- `dbapi_level`
- `libpq_version`
- `driver_paramstyle`
- `opentelemetry_values`

You can exclude any of these keys by passing a dictionary with those keys and the value `False` to `commenter_options`,
e.g:

```python
import logfire

logfire.instrument_psycopg(enable_commenter=True, commenter_options={'db_driver': False, 'dbapi_threadsafety': False})
```

[opentelemetry-psycopg]: https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/psycopg/psycopg.html
[opentelemetry-psycopg2]: https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/psycopg2/psycopg2.html
[psycopg]: https://www.psycopg.org/
