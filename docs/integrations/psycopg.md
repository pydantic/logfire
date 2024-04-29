# Psycopg

The [`logfire.instrument_psycopg()`][logfire.Logfire.instrument_psycopg] function can be used to instrument [Psycopg][psycopg] PostgreSQL driver with **Logfire**. It works with both the `psycopg2` and `psycopg` (i.e. Psycopg 3) packages.

See the documentation for the [OpenTelemetry Psycopg Instrumentation][opentelemetry-psycopg] or the [OpenTelemetry Psycopg2 Instrumentation][opentelemetry-psycopg2] package for more details.

## Installation

Install `logfire` with the `psycopg` extra:

{{ install_logfire(extras=['psycopg']) }}

Or with the `psycopg2` extra:

{{ install_logfire(extras=['psycopg2']) }}

## Usage

Let's setup a PostgreSQL database using Docker and run a Python script that connects to the database using Psycopg to
demonstrate how to use **Logfire** with Psycopg.

### Setup a PostgreSQL Database Using Docker

First, we need to initialize a PostgreSQL database. This can be easily done using Docker with the following command:

```bash
docker run --name postgres \
    -e POSTGRES_USER=user \
    -e POSTGRES_PASSWORD=secret \
    -e POSTGRES_DB=database \
    -p 5432:5432 -d postgres
```

This command accomplishes the following:

- `--name postgres`: This defines the name of the Docker container.
- `-e POSTGRES_USER=user`: This sets a user for the PostgreSQL server.
- `-e POSTGRES_PASSWORD=secret`: This sets a password for the PostgreSQL server.
- `-e POSTGRES_DB=database`: This creates a new database named "database", the same as the one used in your Python script.
- `-p 5432:5432`: This makes the PostgreSQL instance available on your local machine under port 5432.
- `-d postgres`: This denotes the Docker image to be used, in this case, "postgres".

### Run the Python script

The following Python script connects to the PostgreSQL database and executes some SQL queries:

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

connection = psycopg.connect('dbname=database user=user password=secret host=0.0.0.0 port=5432')

# Or instrument just the connection:
logfire.instrument_psycopg(connection)

with logfire.span('Create table and insert data'), connection.cursor() as cursor:
    cursor.execute('CREATE TABLE IF NOT EXISTS test (id serial PRIMARY KEY, num integer, data varchar);')

    # Insert some data
    cursor.execute('INSERT INTO test (num, data) VALUES (%s, %s)', (100, 'abc'))
    cursor.execute('INSERT INTO test (num, data) VALUES (%s, %s)', (200, 'def'))

    # Query the data
    cursor.execute('SELECT * FROM test')
```

If you go to your project on the UI, you will see the span created by the script.

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
