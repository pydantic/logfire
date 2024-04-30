# asyncpg

The [`logfire.instrument_asyncpg()`][logfire.Logfire.instrument_asyncpg] function can be used to instrument the [asyncpg][asyncpg] PostgreSQL driver with **Logfire**.

## Installation

Install `logfire` with the `asyncpg` extra:

{{ install_logfire(extras=['asyncpg']) }}

## Usage

Let's setup a PostgreSQL database using Docker and run a Python script that connects to the database using asyncpg to
demonstrate how to use **Logfire** with asyncpg.

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

```py
import asyncio

import asyncpg

import logfire

logfire.configure()
logfire.instrument_asyncpg()


async def main():
    connection: asyncpg.Connection = await asyncpg.connect(
        user='user', password='secret', database='database', host='0.0.0.0', port=5432
    )

    with logfire.span('Create table and insert data'):
        await connection.execute('CREATE TABLE IF NOT EXISTS test (id serial PRIMARY KEY, num integer, data varchar);')

        # Insert some data
        await connection.execute('INSERT INTO test (num, data) VALUES ($1, $2)', 100, 'abc')
        await connection.execute('INSERT INTO test (num, data) VALUES ($1, $2)', 200, 'def')

        # Query the data
        for record in await connection.fetch('SELECT * FROM test'):
            logfire.info('Retrieved {record=}', record=record)


asyncio.run(main())
```

If you go to your project on the UI, you will see the span created by the script.

[opentelemetry-asyncpg]: https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/asyncpg/asyncpg.html
[opentelemetry-asyncpg2]: https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/asyncpg2/asyncpg2.html
[asyncpg]: https://magicstack.github.io/asyncpg/
