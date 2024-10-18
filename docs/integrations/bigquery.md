# BigQuery

To start sending data to **Logfire**, you need to install the [Google Cloud BigQuery Python client library][bigquery-pypi].

Let's see an example:

```bash
from google.cloud import bigquery

import logfire

logfire.configure()

client = bigquery.Client()
query = 'SELECT name FROM `bigquery-public-data.usa_names.usa_1910_2013` ' 'WHERE state = "TX" ' 'LIMIT 100'
query_job = client.query(query)
query_job.result()
```

You can find more information about the BigQuery Python client library in the [official documentation][bigquery].

[bigquery-otel]: https://cloud.google.com/python/docs/reference/bigquery/latest#instrumenting-with-opentelemetry
[bigquery]: https://cloud.google.com/python/docs/reference/bigquery/latest
[bigquery-pypi]: https://pypi.org/project/google-cloud-bigquery/
