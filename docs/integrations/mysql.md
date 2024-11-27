# MySQL

The [`logfire.instrument_mysql()`][logfire.Logfire.instrument_mysql] method can be used to instrument the [MySQL Connector/Python][mysql-connector] database driver with **Logfire**, creating a span for every query.

## Installation

Install `logfire` with the `mysql` extra:

{{ install_logfire(extras=['mysql']) }}

## Usage

Let's setup a MySQL database using Docker and run a Python script that connects to the database using MySQL connector to
demonstrate how to use **Logfire** with MySQL.

### Setup a MySQL Database Using Docker

First, we need to initialize a MySQL database. This can be easily done using Docker with the following command:

```bash
docker run --name mysql \
    -e MYSQL_ROOT_PASSWORD=secret \
    -e MYSQL_DATABASE=database \
    -e MYSQL_USER=user \
    -e MYSQL_PASSWORD=secret \
    -p 3306:3306 \
    -d mysql
```

The command above will create a MySQL database, that you can connect with `mysql://user:secret@0.0.0.0:3306/database`.

### Run the Python script

The following Python script connects to the MySQL database and executes some SQL queries:

```py
import logfire
import mysql.connector

logfire.configure()

# To instrument the whole module:
logfire.instrument_mysql()

connection = mysql.connector.connect(
    host="localhost",
    user="user",
    password="secret",
    database="database",
    port=3306,
    use_pure=True,
)

# Or instrument just the connection:
# connection = logfire.instrument_mysql(connection)

with logfire.span('Create table and insert data'), connection.cursor() as cursor:
    cursor.execute(
        'CREATE TABLE IF NOT EXISTS test (id INT AUTO_INCREMENT PRIMARY KEY, num integer, data varchar(255));'
    )

    # Insert some data
    cursor.execute('INSERT INTO test (num, data) VALUES (%s, %s)', (100, 'abc'))
    cursor.execute('INSERT INTO test (num, data) VALUES (%s, %s)', (200, 'def'))

    # Query the data
    cursor.execute('SELECT * FROM test')
    results = cursor.fetchall()  # Fetch all rows
    for row in results:
        print(row)  # Print each row
```

[`logfire.instrument_mysql()`][logfire.Logfire.instrument_mysql] uses the
**OpenTelemetry MySQL Instrumentation** package,
which you can find more information about [here][opentelemetry-mysql].

[opentelemetry-mysql]: https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/mysql/mysql.html
[mysql]: https://www.mysql.com/
[mysql-connector]: https://dev.mysql.com/doc/connector-python/en/
