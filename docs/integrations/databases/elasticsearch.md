---
title: "Instrument Elasticsearch: trace searches and other requests"
description: "Trace requests made by the Elasticsearch Python client 8.15 and later with its native OpenTelemetry support."
integration: otel
---
# Elasticsearch

See every request your application makes to Elasticsearch, including its operation, duration,
outcome, and target, as a **span** (one unit of work: a single operation, with a name, a start, and a
duration) in Logfire.

The Elasticsearch Python client has native **OpenTelemetry (OTel)** support from version 8.15. OTel
is the open industry standard for collecting traces, metrics, and logs. The client creates its own
spans through the active global tracer provider, so you do not need a Logfire wrapper or the older
`opentelemetry-instrumentation-elasticsearch` package.

{{ before_you_start() }}

## Install the client

Install Logfire and Elasticsearch 8.15 or later:

```bash
pip install 'logfire' 'elasticsearch>=8.15'
```

## Trace Elasticsearch requests

Call `logfire.configure()` before making an Elasticsearch request. The client looks up the active
OTel tracer provider when it starts a request, so you can create the client before or after this call.

```python skip-run="true" skip-reason="external-connection"
from elasticsearch import Elasticsearch

import logfire

client = Elasticsearch('http://localhost:9200')

logfire.configure()
client.search(index='products', query={'match': {'name': 'coffee'}})
```

## Control whether search queries are recorded

By default, the client does not attach the search query body to spans because it can contain
sensitive or personally identifiable information (PII). To record query bodies, set this environment
variable before starting your application:

```bash
export OTEL_PYTHON_INSTRUMENTATION_ELASTICSEARCH_CAPTURE_SEARCH_QUERY=raw
```

!!! warning
    Setting this option to `raw` sends query values to Logfire, where they are stored with the span.
    Logfire does not scrub the `db.query.text` attribute. Enable query capture only when the queries
    do not contain sensitive values.

## Stop tracing Elasticsearch requests

The Elasticsearch client creates spans by default whenever an OTel tracer provider is active. To
turn off its native tracing, set this environment variable before creating the client:

```bash
export OTEL_PYTHON_INSTRUMENTATION_ELASTICSEARCH_ENABLED=false
```

## Verify the spans

Run the application and open Logfire's [Live view](../../guides/web-ui/live.md). Search for
`elasticsearch` and make a request. You should see an Elasticsearch span with the request method,
target, duration, and status. If query capture is enabled, the span also contains the search query
body.

## Troubleshoot missing spans

- **No Elasticsearch spans appear:** check that you use `elasticsearch` 8.15 or later, call
  `logfire.configure()` before the first request, and have not set
  `OTEL_PYTHON_INSTRUMENTATION_ELASTICSEARCH_ENABLED=false`.
- **The query body is missing:** restart the application after setting
  `OTEL_PYTHON_INSTRUMENTATION_ELASTICSEARCH_CAPTURE_SEARCH_QUERY=raw`. Query capture is disabled by
  default.
- **Duplicate spans appear:** remove `opentelemetry-instrumentation-elasticsearch` and its setup. The
  client already creates spans natively.

## Reference

- [Elasticsearch Python client OpenTelemetry documentation](https://www.elastic.co/docs/reference/elasticsearch/clients/python/opentelemetry)
