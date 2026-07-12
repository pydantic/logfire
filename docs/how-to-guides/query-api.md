---
title: Guide to Exporting Logfire Data via Web API
description: "Leverage the Logfire web API to query data via SQL. Export logs & metrics and retrieve data in JSON, CSV, or Apache Arrow format."
---
**Logfire** provides a web API for programmatically running arbitrary SQL queries against the data in your **Logfire** projects.
This API can be used to retrieve data for export, analysis, or integration with other tools, allowing you to leverage
your data in a variety of ways.

The API endpoint expects a POST request and is available at:

* `https://logfire-us.pydantic.dev/v2/query` for the US [region](../reference/data-regions.md).
* `https://logfire-eu.pydantic.dev/v2/query` for the EU [region](../reference/data-regions.md).

It requires a **read token** for authentication, which can be generated from the Logfire web interface and provide secure access to your data.

The API can return data in various formats, including JSON, Apache Arrow, and CSV, to suit your needs.
See [here](#additional-configuration) for more details about the available response formats.

## How to Create a Read Token

If you've set up Logfire following the [getting started guide](../index.md), you can generate read tokens either from
the Logfire web interface or via the CLI.

### Via Web Interface

To create a read token using the web interface:

1. Open the **Logfire** web interface at [logfire.pydantic.dev](https://logfire.pydantic.dev).
2. Select your project from the **Projects** section on the left-hand side of the page.
3. Click on the ⚙️ **Settings** tab in the top right corner of the page.
4. Select the **Read tokens** tab from the left-hand menu.
5. Click on the **Create read token** button.

After creating the read token, you'll see a dialog with the token value.
**Copy this value and store it securely, it will not be shown again.**

### Via CLI

You can also create read tokens programmatically using the Logfire CLI:

```bash
logfire read-tokens --project <organization>/<project> create
```

This command will output the read token directly to stdout, making it convenient for use in scripts.

## Using the Read Clients

While you can [make direct HTTP requests](#making-direct-http-requests) to Logfire's querying API,
we provide Python clients to simplify the process of interacting with the API from Python.

Logfire provides both synchronous and asynchronous clients.
To use these clients, you can import them from the `query_client` module:

```python skip="true" skip-reason="incomplete"
from logfire.query_client import AsyncLogfireQueryClient, LogfireQueryClient
```

!!! note "Additional required dependencies"

    To use the query clients provided in `logfire.query_client`, you need to install [`httpx`](https://pypi.org/project/httpx/).

    If you want to retrieve Arrow-format responses, you will also need to install [`pyarrow`](https://pypi.org/project/pyarrow/).

### Client Usage Examples

The [`AsyncLogfireQueryClient`][logfire.query_client.AsyncLogfireQueryClient] allows for asynchronous interaction with
the Logfire API. If blocking I/O is acceptable and you want to avoid the complexities of asynchronous programming,
you can use the plain [`LogfireQueryClient`][logfire.query_client.LogfireQueryClient].

Here's an example of how to use these clients:

/// version-deprecated | v4.35.0
The older `query_json()` method is deprecated in favor of `query_json_rows()`. Calling `query_json_rows()`,
`query_arrow()`, or `query_csv()` without providing a `min_timestamp` is also deprecated: pass an explicit
timestamp as shown below.
///

=== "Async"

    ```python skip-run="true" skip-reason="external-connection"
    from datetime import UTC, datetime, timedelta
    from io import StringIO

    import polars as pl

    from logfire.query_client import AsyncLogfireQueryClient


    async def main():
        query = """
        SELECT start_timestamp
        FROM records
        LIMIT 1
        """
        min_timestamp = datetime.now(tz=UTC) - timedelta(hours=2)

        async with AsyncLogfireQueryClient(read_token='<your_read_token>') as client:
            # Load data as JSON
            json_rows = await client.query_json_rows(sql=query, min_timestamp=min_timestamp)
            print(json_rows)
            """
            {
                "columns": [{'name': 'start_timestamp', 'datatype': {'Timestamp': ['Microsecond', 'UTC']}, 'nullable': False}],
                "rows":  [{'start_timestamp': '2026-05-27T13:16:36.517321Z'}]
            }
            """

            # Retrieve data in arrow format, and load into a polars DataFrame
            # Note that JSON columns such as `attributes` will be returned as
            # JSON-serialized strings
            df_from_arrow = pl.from_arrow(await client.query_arrow(sql=query, min_timestamp=min_timestamp))
            print(df_from_arrow)

            # Retrieve data in CSV format, and load into a polars DataFrame
            # Note that JSON columns such as `attributes` will be returned as
            # JSON-serialized strings
            df_from_csv = pl.read_csv(StringIO(await client.query_csv(sql=query, min_timestamp=min_timestamp)))
            print(df_from_csv)

            # Get read token info
            read_token_info = await client.info()
            print(read_token_info)


    if __name__ == '__main__':
        import asyncio

        asyncio.run(main())
    ```

=== "Sync"

    ```python skip-run="true" skip-reason="external-connection"
    from datetime import UTC, datetime, timedelta
    from io import StringIO

    import polars as pl

    from logfire.query_client import LogfireQueryClient


    def main():
        query = """
        SELECT start_timestamp
        FROM records
        LIMIT 1
        """
        min_timestamp = datetime.now(tz=UTC) - timedelta(hours=2)

        with LogfireQueryClient(read_token='<your_read_token>') as client:
            # Load data as JSON
            json_rows = client.query_json_rows(sql=query, min_timestamp=min_timestamp)
            print(json_rows)
            """
            {
              "columns": [{'name': 'start_timestamp', 'datatype': {'Timestamp': ['Microsecond', 'UTC']}, 'nullable': False}],
              "rows":  [{'start_timestamp': '2026-05-27T13:16:36.517321Z'}]
            }
            """

            # Retrieve data in arrow format, and load into a polars DataFrame
            # Note that JSON columns such as `attributes` will be returned as
            # JSON-serialized strings
            df_from_arrow = pl.from_arrow(client.query_arrow(sql=query, min_timestamp=min_timestamp))
            print(df_from_arrow)

            # Retrieve data in CSV format, and load into a polars DataFrame
            # Note that JSON columns such as `attributes` will be returned as
            # JSON-serialized strings
            df_from_csv = pl.read_csv(StringIO(client.query_csv(sql=query, min_timestamp=min_timestamp)))
            print(df_from_csv)

            # Get read token info
            read_token_info = client.info()
            print(read_token_info)


    if __name__ == '__main__':
        main()
    ```

## DB API 2.0 Interface

Logfire also provides a [PEP 249](https://peps.python.org/pep-0249/) (DB API 2.0) compatible interface via
`logfire.db_api`. This makes Logfire query data work out of the box with any tool that supports standard
Python database connections, including [pandas](https://pandas.pydata.org/docs/reference/api/pandas.read_sql.html),
[marimo SQL cells](https://docs.marimo.io/guides/working_with_data/sql/), and Jupyter `%%sql` magic.

### Basic Usage

```python skip-run="true" skip-reason="external-connection"
import logfire.db_api

conn = logfire.db_api.connect(read_token='<your_read_token>')
cursor = conn.cursor()
cursor.execute('SELECT start_timestamp, message FROM records LIMIT 10')
rows = cursor.fetchall()
print(rows)
conn.close()
```

The connection can also be used as a context manager:

```python skip-run="true" skip-reason="external-connection"
import logfire.db_api

with logfire.db_api.connect(read_token='<your_read_token>') as conn:
    cursor = conn.cursor()
    cursor.execute('SELECT start_timestamp, message FROM records LIMIT 10')
    print(cursor.fetchall())
```

### Using with pandas

```python skip-run="true" skip-reason="external-connection"
import pandas as pd

import logfire.db_api

conn = logfire.db_api.connect(read_token='<your_read_token>')
df = pd.read_sql('SELECT start_timestamp, message FROM records LIMIT 100', conn)
print(df)
conn.close()
```

!!! note "pandas warning about non-SQLAlchemy connections"

    You may see a warning from pandas:

    > `UserWarning: pandas only supports SQLAlchemy connectable (engine/connection) or database string URI or sqlite3 DBAPI2 connection. Other DBAPI2 objects are not tested. Please consider using SQLAlchemy.`

    This is safe to ignore. pandas uses the standard DB API 2.0 cursor interface under the hood and
    it works correctly with `logfire.db_api`. The warning just means pandas hasn't explicitly tested
    third-party DB API connections. If you do run into any issues, please
    [open an issue](https://github.com/pydantic/logfire/issues).

### Using with marimo

In a [marimo](https://marimo.io/) notebook, you can register the connection and then use SQL cells directly:

```python skip-run="true" skip-reason="incomplete"
import logfire.db_api

conn = logfire.db_api.connect(read_token='<your_read_token>')
# Register connection with marimo; now you can use SQL cells with the "logfire" connection
```

### Parameters

The DB API module supports `pyformat`-style parameters (`%(name)s` placeholders):

```python skip-run="true" skip-reason="external-connection"
import logfire.db_api

with logfire.db_api.connect(read_token='<your_read_token>') as conn:
    cursor = conn.cursor()
    cursor.execute(
        'SELECT message FROM records WHERE service_name = %(service)s LIMIT 10',
        {'service': 'my-app'},
    )
    print(cursor.fetchall())
```

### Row Limits

By default, the DB API module requests up to 10,000 rows per query.
If the number of returned rows equals the limit, a warning is emitted suggesting you add explicit
`LIMIT`/`OFFSET` clauses to your SQL. You can customize the default limit:

```python skip-run="true" skip-reason="external-connection"
import logfire.db_api

# Set a lower default limit
conn = logfire.db_api.connect(read_token='<your_read_token>', limit=1000)

# Or override per-cursor
cursor = conn.cursor()
cursor.limit = 500
```

### Timestamp Filtering

By default, the DB API module only queries data from the **last 24 hours**. This keeps queries fast and avoids
accidentally scanning large amounts of data. If you need to query older data, set `min_timestamp` explicitly:

```python skip-run="true" skip-reason="external-connection"
from datetime import timedelta

import logfire.db_api

# Query the last 7 days
conn = logfire.db_api.connect(read_token='<your_read_token>', min_timestamp=timedelta(days=7))
```

You can also override the timestamp filter per-cursor:

```python skip-run="true" skip-reason="external-connection"
from datetime import datetime, timedelta, timezone

import logfire.db_api

conn = logfire.db_api.connect(read_token='<your_read_token>')
cursor = conn.cursor()
cursor.min_timestamp = datetime.now(timezone.utc) - timedelta(days=14)
cursor.execute('SELECT start_timestamp, message FROM records LIMIT 10')
```

/// version-deprecated | v4.35.0
Setting `min_timestamp` to `None` in `connect()` or on the cursor is deprecated.
///

## Making Direct HTTP Requests

If you prefer not to use the provided clients, you can make direct HTTP requests to the Logfire API using any HTTP
client library, such as [`requests`](https://pypi.org/project/requests/) in Python. Below are the general steps and an example to guide you:

### General Steps to Make a Direct HTTP Request

1. **Set the Endpoint URL**: The base URL for the Logfire API is `https://logfire-us.pydantic.dev` for accounts in the US region, and `https://logfire-eu.pydantic.dev` for accounts in the EU region.

2. **Add Authentication**: Include the read token in your request headers to authenticate.
   The header key should be `Authorization` with the value `Bearer <your_read_token_here>`.

3. **Define the SQL Query**: Write the SQL query you want to execute.

4. **Send the Request**: Use an HTTP POST request to the `/v2/query` endpoint with the SQL query in the JSON request body.

**Note:** You can provide additional body parameters to control the behavior of your requests.
You can also use the `Accept` header to specify the desired format for the response data (JSON, Arrow, or CSV).

### Example: Using Python `requests` Library

```python skip-run="true" skip-reason="external-connection"
from datetime import UTC, datetime, timedelta

import requests

# Define the base URL and your read token
base_url = 'https://logfire-us.pydantic.dev'  # or 'https://logfire-eu.pydantic.dev' for EU accounts
read_token = '<your_read_token_here>'

# Set the headers for authentication
headers = {'Authorization': f'Bearer {read_token}'}

# Define your SQL query
query = """
SELECT start_timestamp
FROM records
LIMIT 1
"""

# Prepare the body for the POST request
min_timestamp = datetime.now(tz=UTC) - timedelta(hours=2)
body = {'sql': query, 'min_timestamp': min_timestamp.isoformat()}

# Send the POST request to the Logfire API
response = requests.post(f'{base_url}/v2/query', json=body, headers=headers)

# Check the response status
if response.status_code == 200:
    print('Query Successful!')
    print(response.json())
else:
    print(f'Failed to execute query. Status code: {response.status_code}')
    print(response.text)
```

### Additional Configuration

The Logfire API supports various response formats and body parameters to give you flexibility in how you retrieve your data:

- **Response Format**: Use the `Accept` header to specify the response format. Supported values include:
    - `application/json`: Returns the data in JSON format, with two entries:
      - `schema`: Information about the result schema. This is an object with a `fields` entry, listing column details including the name,
      datatype and whether the column is nullable (e.g. `{"schema": {"fields": [{"name": "service_name", "data_type":  "Utf8", "nullable": false}]}}`).
      - `data`: The list of rows matching the query (e.g. `[{"service_name": "backend"}]`).
    - `application/x-ndjson`: Returns the data in NDJSON format, in a streaming fashion (see format of messages below).
    - `application/vnd.apache.arrow.stream`: Returns the data in Apache Arrow format, suitable for high-performance data processing.
    - `text/csv`: Returns the data in CSV format, which is easy to use with many data tools.
    - If no `Accept` header is provided, the default response format is JSON.
- **Body Parameters**:
    - **`sql`**: The SQL query to execute. This parameter is required.
    - **`min_timestamp`**: An ISO-format timestamp to filter records with `start_timestamp` greater than this value for the `records` table
      or `recorded_timestamp` greater than this value for the `metrics` table. The same filtering can also be done manually within the query itself.
      This parameter is required.
    - **`max_timestamp`**: Similar to `min_timestamp`, but serves as an upper bound for filtering `start_timestamp` in the `records` table or `recorded_timestamp` in the `metrics` table. The same filtering can also be done manually within the query itself.
    - **`limit`**: An optional parameter to limit the number of rows returned by the query. If not specified, **the default limit is 100**. The maximum allowed value is 10,000.
    - **`timezone`**: An optional timezone (e.g. `"Europe/Paris"`) to use for the query execution context.
    - **`deployment_environment`**: Restrict rows to one or more [environments](environments.md). Accepts a list of environment name strings (the Python client's `environment` argument also accepts a single string). To only match rows where no environment is set, use the empty string (`""`).
    - **`explain`**: Whether to explain the query or not.

All body parameters besides `sql` and `min_timestamp` are optional and can be used in any combination to tailor the API response to your needs.

### NDJSON Response Format

When you request the `application/x-ndjson` response format, the response body is streamed as
[newline-delimited JSON](https://github.com/ndjson/ndjson-spec): each line is a self-contained JSON object
terminated by a newline (`\n`). Every object has a `type` field that identifies the kind of message, allowing
you to process results incrementally as they arrive rather than waiting for the full response.

The following message types may be emitted:

#### `schema`

Describes the columns of the result set. It is emitted before any data rows.

| Field    | Type   | Description                                                                                                              |
| -------- | ------ | ------------------------------------------------------------------------------------------------------------------------ |
| `type`   | string | Always `"schema"`.                                                                                                       |
| `schema` | object | The result schema. Has a `fields` entry listing each column's `name`, `data_type`, and whether it is `nullable`. |

```json
{"type": "schema", "schema": {"fields": [{"name": "service_name", "data_type": "Utf8", "nullable": false}]}}
```

#### `explain`

Emitted only when the `explain` body parameter is set to `true`. Carries the query plans.

| Field           | Type   | Description                              |
| --------------- | ------ | ---------------------------------------- |
| `type`          | string | Always `"explain"`.                      |
| `logical_plan`  | any    | The logical query plan.                  |
| `physical_plan` | any    | The physical query plan.                 |

#### `data`

Carries a batch of result rows. Multiple `data` messages may be emitted for a single query, each containing a
chunk of the overall result.

| Field  | Type             | Description                                                               |
| ------ | ---------------- | ------------------------------------------------------------------------- |
| `type` | string           | Always `"data"`.                                                          |
| `rows` | array of objects | A batch of result rows, where each row maps column names to their values. |

```json
{"type": "data", "rows": [{"service_name": "backend"}, {"service_name": "frontend"}]}
```

#### `error`

Emitted if an error occurs while executing the query. The stream may end after an `error` message.

| Field     | Type   | Description                          |
| --------- | ------ | ------------------------------------ |
| `type`    | string | Always `"error"`.                    |
| `message` | string | A human-readable error description.  |

```json
{"type": "error", "message": "Invalid SQL: ..."}
```

#### `end`

The final message of a successful stream, signalling that all data has been sent.

| Field                        | Type    | Description                                                                            |
| ---------------------------- | ------- | -------------------------------------------------------------------------------------- |
| `type`                       | string  | Always `"end"`.                                                                        |
| `row_count`                  | integer | The total number of rows returned across all `data` messages.                          |
| `physical_plan_with_metrics` | any     | *(Optional)* The physical query plan annotated with execution metrics, when available. |

```json
{"type": "end", "row_count": 2}
```
