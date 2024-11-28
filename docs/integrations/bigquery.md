# BigQuery

The [Google Cloud BigQuery Python client library][bigquery-pypi] is instrumented with OpenTelemetry out of the box,
and all the extra dependencies are already included with **Logfire** by default, so you only need to call `logfire.configure()`.

??? question "What if I don't want to instrument BigQuery?"
    Since BigQuery automatically instruments itself, you need to opt-out of instrumentation
    if you don't want to use it.

    To do it, you'll need to call [`logfire.suppress_scopes()`][logfire.Logfire.suppress_scopes]
    with the scope `google.cloud.bigquery.opentelemetry_tracing`.

    ```python
    import logfire

    logfire.configure()
    logfire.suppress_scopes("google.cloud.bigquery.opentelemetry_tracing")
    ```


Let's see an example:

```python
from google.cloud import bigquery

import logfire

logfire.configure()

client = bigquery.Client()
query = """
SELECT name
FROM `bigquery-public-data.usa_names.usa_1910_2013`
WHERE state = "TX"
LIMIT 100
"""
query_job = client.query(query)
print(list(query_job.result()))
```

You can find more information about the BigQuery Python client library in the [official documentation][bigquery].

[bigquery]: https://cloud.google.com/python/docs/reference/bigquery/latest
[bigquery-pypi]: https://pypi.org/project/google-cloud-bigquery/
