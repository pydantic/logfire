# SQLite3

The [`logfire.instrument_sqlite3()`][logfire.Logfire.instrument_sqlite3] method can be used to instrument the
[SQLite3][sqlite3] standard library module. This will automatically create spans for each SQL query executed.

## Installation

Install `logfire` with the `sqlite3` extra:

{{ install_logfire(extras=['sqlite3']) }}

## Usage

We can use the sqlite in memory database to demonstrate the usage of the
[`logfire.instrument_sqlite3()`][logfire.Logfire.instrument_sqlite3] method.

=== "Instrument the package"

    ```py title="main.py"
    import sqlite3

    import logfire

    logfire.configure()
    logfire.instrument_sqlite3()

    with sqlite3.connect(':memory:') as connection:
        cursor = connection.cursor()

        cursor.execute('CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT)')
        cursor.execute("INSERT INTO users (name) VALUES ('Alice')")

        cursor.execute('SELECT * FROM users')
        print(cursor.fetchall())
        # > [(1, 'Alice')]
    ```

=== "Instrument the connection"

    ```py title="main.py"
    import sqlite3

    import logfire

    logfire.configure()

    with sqlite3.connect(':memory:') as connection:
        connection = logfire.instrument_sqlite3(connection)
        cursor = connection.cursor()

        cursor.execute('CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT)')
        cursor.execute("INSERT INTO users (name) VALUES ('Alice')")

        cursor.execute('SELECT * FROM users')
        print(cursor.fetchall())
        # > [(1, 'Alice')]
    ```

[`logfire.instrument_sqlite3()`][logfire.Logfire.instrument_sqlite3] uses the
**OpenTelemetry SQLite3 Instrumentation** package,
which you can find more information about [here][opentelemetry-sqlite3].

[opentelemetry-sqlite3]: https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/sqlite3/sqlite3.html
[sqlite3]: https://docs.python.org/3/library/sqlite3.html
[mysql-connector]: https://dev.mysql.com/doc/connector-python/en/
