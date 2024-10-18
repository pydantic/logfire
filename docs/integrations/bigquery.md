# BigQuery

The [Google Cloud BigQuery Python client library][bigquery-pypi] is instrumented with OpenTelemetry out of the box,
and all the extra dependencies are already included with **Logfire** by default, so you only need to call `logfire.configure()`.

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
