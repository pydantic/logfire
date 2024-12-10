# SQLite3

The [`logfire.instrument_sqlite3()`][logfire.Logfire.instrument_sqlite3] method can be used to instrument the
[`sqlite3`][sqlite3] standard library module. This will automatically create spans for each SQL query executed.

## Installation

Install `logfire` with the `sqlite3` extra:

{{ install_logfire(extras=['sqlite3']) }}

## Usage

We can use the sqlite in-memory database to demonstrate the usage of the
[`logfire.instrument_sqlite3()`][logfire.Logfire.instrument_sqlite3] method.

You can either instrument the `sqlite3` module or instrument a specific connection.

### Instrument the module

Here's an example of instrumenting the [`sqlite3`][sqlite3] module:

```py title="main.py" hl_lines="6"
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

### Instrument a connection

As mentioned, you can also instrument a specific connection. Here's an example:

```py title="main.py" hl_lines="8"
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

!!! warning "Avoid using `execute` from `sqlite3.Connection`"
    The [`execute`][sqlite3.Connection.execute] method from [`Connection`][sqlite3.Connection] is not instrumented!

    You should use the [`execute`][sqlite3.Cursor.execute] method from the [`Cursor`][sqlite3.Cursor] object instead.

    See [opentelemetry-python-contrib#3082](https://github.com/open-telemetry/opentelemetry-python-contrib/issues/3082)
    for more information.

[`logfire.instrument_sqlite3()`][logfire.Logfire.instrument_sqlite3] uses the
**OpenTelemetry SQLite3 Instrumentation** package,
which you can find more information about [here][opentelemetry-sqlite3].

[opentelemetry-sqlite3]: https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/sqlite3/sqlite3.html
[sqlite3]: https://docs.python.org/3/library/sqlite3.html
[mysql-connector]: https://dev.mysql.com/doc/connector-python/en/
