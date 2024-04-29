# Psycopg2

The [OpenTelemetry Instrumentation Psycopg2][opentelemetry-psycopg2] package can be used to instrument [Psycopg2][psycopg2].

## Installation

Install `logfire` with the `psycopg2` extra:

{{ install_logfire(extras=['psycopg2']) }}

## Usage

Let's setup a PostgreSQL database using Docker and run a Python script that connects to the database using Psycopg2 to
demonstrate how to use **Logfire** with Psycopg2.

1. Setup a PostgreSQL Database Using Docker

First, we need to initialize a PostgreSQL database. This can be easily done using Docker with the following command:

```bash
docker run --name postgres \
    -e POSTGRES_USER=user \
    -e POSTGRES_PASSWORD=secret \
    -e POSTGRES_DB=database \
    -p 5432:5432 -d postgres
```

This command accomplishes the following:

• `--name postgres`: This defines the name of the Docker container.
• `-e POSTGRES_USER=user`: This sets a user for the PostgreSQL server.
• -e `POSTGRES_PASSWORD=secret`: This sets a password for the PostgreSQL server.
• `-e POSTGRES_DB=database`: This creates a new database named "database", the same as the one used in your Python script.
• `-p 5432:5432`: This makes the PostgreSQL instance available on your local machine under port 5432.
• `-d postgres`: This denotes the Docker image to be used, in this case, "postgres".

2. Run the Python script

The following Python script connects to the PostgreSQL database and executes some SQL queries:

```py
import logfire
import psycopg2
from opentelemetry.instrumentation.psycopg2 import Psycopg2Instrumentor

logfire.configure()
Psycopg2Instrumentor().instrument()

conn = psycopg2.connect(database='database', user='user', password='secret', host='0.0.0.0', port='5433')

with logfire.span('Create table and insert data'), conn.cursor() as cursor:
    cursor.execute('CREATE TABLE IF NOT EXISTS test (id serial PRIMARY KEY, num integer, data varchar);')

    # Insert some data
    cursor.execute('INSERT INTO test (num, data) VALUES (%s, %s)', (100, 'abc'))
    cursor.execute('INSERT INTO test (num, data) VALUES (%s, %s)', (200, 'def'))

    # Query the data
    cursor.execute('SELECT * FROM test')
```

If you go to your project on the UI, you will see the span created by the script.

Feel free to read more about the Psycopg2 OpenTelemetry package on the official [documentation][opentelemetry-psycopg2].

!!! bug
    A bug occurs when `opentelemetry-instrumentation-psycopg2` is used with `psycopg2-binary` instead of `psycopg2`.
    More details on the issue can be found [here][psycopg2-binary-issue].

    A workaround is to include `skip_dep_check` in `instrument` method:

    ```py
    from opentelemetry.instrumentation.psycopg2 import Psycopg2Instrumentor

    Psycopg2Instrumentor().instrument(skip_dep_check=True)
    ```

[opentelemetry-psycopg2]: https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/psycopg2/psycopg2.html
[psycopg2]: https://www.psycopg.org/
[psycopg2-binary-issue]: https://github.com/open-telemetry/opentelemetry-python-contrib/issues/610
