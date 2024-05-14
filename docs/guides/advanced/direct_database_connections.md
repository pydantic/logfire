# Direct Database Connections

The **Logfire** platform allows you to connect and run SQL queries against your data using PostgreSQL syntax.

By doing this, you can connect your existing tools such as Grafana, Metabase, Superset, or anything else with support for querying PostgreSQL sources.

## Generating credentials

To connect, you'll first need to generate generate database credentials from your project page at `https://logfire.pydantic.dev/<organization>/<project>/settings/database-credentials`

![Creating database credentials](../../images/guide/direct-connect-credentials.png)

The credentials generated are a PostgreSQL URI which can be used as a connection string for compatible tools. These will only be shown by the Logfire platform once, so save them to a secure location for future use!

## Connecting to the database

As mentioned, you can use the generated credentials to connect to the database using any tool that supports PostgreSQL connections.

### Using `pgcli`

[`pgcli`](https://www.pgcli.com/) is a command-line tool to access PostgreSQL databases.

Using the credentials generated in the previous step as the argument to `pgcli`, you can connect directly to **Logfire**:

```bash
$ pgcli postgresql://<user>:<password>@db.logfire.dev:5432/proj_david-test  # REDACTED
Version: 4.0.1
Home: http://pgcli.com
proj_david-test> select start_timestamp, message from records limit 10;
+-------------------------------+----------------------------------------+
| start_timestamp               | message                                |
|-------------------------------+----------------------------------------|
| 2024-04-28 10:50:41.681886+00 | action=view-faq size=549 i=0           |
| 2024-04-28 10:50:41.711747+00 | GET /contact/ http send response.body  |
| 2024-04-28 10:50:41.665576+00 | GET /contact/                          |
| 2024-04-28 10:50:41.711119+00 | GET /contact/ http send response.start |
| 2024-04-28 10:50:41.709458+00 | response 500                           |
| 2024-04-28 10:50:38.505343+00 | action=view-cart size=517 i=0          |
| 2024-04-28 10:50:39.446668+00 | action=view-faq size=637 i=2           |
| 2024-04-28 10:50:38.681198+00 | action=view-terms size=216 i=3         |
| 2024-04-28 10:50:39.416706+00 | action=view-product size=380 i=0       |
| 2024-04-28 10:50:38.394237+00 | sub-sub-sub-action=logout              |
+-------------------------------+----------------------------------------+
SELECT 10
Time: 0.218s
```

### Using `psycopg`

[`psycopg`](https://www.psycopg.org/) is a Python library that allows you to connect to PostgreSQL databases.

You can use the credentials generated in the previous step to connect to **Logfire**:

```python title='main.py'
import os

import psycopg

POSTGRES_URI = os.getenv('POSTGRES_URI')

with psycopg.connect(POSTGRES_URI) as conn:
    cursor = conn.cursor()
    cursor.execute('SELECT start_timestamp, message FROM records LIMIT 10')
    for start_timestamp, message in cursor.fetchall():
        print(f'{start_timestamp}: {message}')
```

Set the `export POSTGRES_URI=...` environment variable to the URI generated in the previous step, and run the
script with `python main.py`:

```bash
2024-04-28 10:50:41.681886+00: action=view-faq size=549 i=0
2024-04-28 10:50:41.711747+00: GET /contact/ http send response.body
2024-04-28 10:50:41.665576+00: GET /contact/
2024-04-28 10:50:41.711119+00: GET /contact/ http send response.start
2024-04-28 10:50:41.709458+00: response 500
2024-04-28 10:50:38.505343+00: action=view-cart size=517 i=0
2024-04-28 10:50:39.446668+00: action=view-faq size=637 i=2
2024-04-28 10:50:38.681198+00: action=view-terms size=216 i=3
2024-04-28 10:50:39.416706+00: action=view-product size=380 i=0
2024-04-28 10:50:38.394237+00: sub-sub-sub-action=logout
```

With the flexibility of PostgreSQL access available to you, we can't wait to hear what you do with **Logfire**! :fire:
