---
title: "Instrument BigQuery: trace every query and job"
description: "See each BigQuery query your app runs in Logfire, with its duration and job status. Instrumented automatically once you call logfire.configure()."
integration: "built-in"
---
# BigQuery

See every query your app sends to Google's [BigQuery][bigquery] data warehouse (the SQL it ran, how
long the job took, and its status) as a **span** (one unit of work with a name, a start, and a
duration) in Logfire. Related spans link together into a **trace** (the full journey of one request),
so a slow query shows up right next to the code that triggered it.

The [Google Cloud BigQuery Python client library][bigquery-pypi] instruments itself through
OpenTelemetry, and everything it needs already ships with Logfire, so you don't add an
`instrument_*` call. Once you call `logfire.configure()`, BigQuery queries start appearing in Logfire
on their own. If you'd rather they didn't, see [Opting out](#opting-out) below.

## What you'll capture

- Each query as a span, with its duration and job status
- The SQL statement that ran
- Failed queries, with the error

## Before you start

You'll need a Logfire project and its **write token**: the credential your app uses to send data to
Logfire. Create a project and copy its token from **Project → Settings → Write tokens** in the
Logfire web app. New to Logfire? Start with [Getting Started](../../index.md), which walks through
creating a project and linking your machine.

## Installation

BigQuery has no separate Logfire extra: the OpenTelemetry support it needs is already included with
Logfire. Install `logfire` (the example below also imports the `google-cloud-bigquery` client, which
you'll already have if you're using BigQuery):

{{ install_logfire() }}

## Usage

Call `logfire.configure()` before you use the BigQuery client. That's the only step: the client
instruments itself, so there's no `logfire.instrument_bigquery()` to call.

```python skip-run="true" skip-reason="external-connection"
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

## Verify it worked

Run a query, then open the [Live view](../../guides/web-ui/live.md). Within a few seconds you'll see a
span for the query, with its duration and job status. Click it to see the SQL that ran.

<!-- TODO(app-verify): screenshot of a BigQuery query span in the Live view, showing the SQL and job status -->

## Advanced

### Opting out

Because BigQuery instruments itself, you opt *out* rather than in. To stop its spans reaching Logfire,
call [`logfire.suppress_scopes()`][logfire.Logfire.suppress_scopes] with the scope
`google.cloud.bigquery.opentelemetry_tracing`:

```python
import logfire

logfire.configure()
logfire.suppress_scopes('google.cloud.bigquery.opentelemetry_tracing')
```

## Troubleshooting

Not seeing your queries? Check that `logfire.configure()` ran before you created the BigQuery client,
that your write token is set (run `logfire projects use <your-project>` locally, or set the
`LOGFIRE_TOKEN` environment variable in production; see [Getting Started](../../index.md)), and that
you haven't suppressed the `google.cloud.bigquery.opentelemetry_tracing` scope.

## Reference

- [Google Cloud BigQuery Python client library][bigquery]: the official documentation.
- [`google-cloud-bigquery`][bigquery-pypi]: the package on PyPI.

[bigquery]: https://cloud.google.com/python/docs/reference/bigquery/latest
[bigquery-pypi]: https://pypi.org/project/google-cloud-bigquery/
