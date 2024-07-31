# MySQL

The [`logfire.instrument_mysql()`][logfire.Logfire.instrument_mysql] function can be used to instrument the [MySQL][mysql] database supporting [MySQL connector][mysql-connector] with **Logfire**.

See the documentation for the [OpenTelemetry MySQL Instrumentation][opentelemetry-mysql].

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
    -p 3306:3306 -d mysql
```

This command accomplishes the following:

- `--name mysql`: gives the container a name of "mysql".
- `-e MYSQL_ROOT_PASSWORD=secret` sets the root password to "secret".
- `-e MYSQL_DATABASE=database` creates a new database named "database".
- `-e MYSQL_USER=user` creates a new user named "user".
- `-e MYSQL_PASSWORD=secret` sets the password for the new user to "secret".
- `-p 3306:3306` maps port 3306 inside Docker as port 3306 on the host machine.
- `-d mysql` runs the container in the background and prints the container ID. The image is "mysql".

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

If you go to your project on the UI, you will see the span created by the script.

[opentelemetry-mysql]: https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/mysql/mysql.html
[mysql]: https://www.mysql.com/
[mysql-connector]: https://dev.mysql.com/doc/connector-python/en/
