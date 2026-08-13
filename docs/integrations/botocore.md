---
title: "Instrument botocore: trace AWS API calls"
description: "Add botocore instrumentation and see each AWS API call in Logfire, including its service, operation, duration, and errors."
integration: otel
---
# Botocore

See every Amazon Web Services (AWS) API call made through botocore or Boto3, including the service,
operation, duration, and errors, as a span (one unit of work: a single operation, with a name, a
start, and a duration) in Logfire.

## What you'll capture

- The AWS service and operation for each call
- The call's duration and result status
- Exceptions raised by failed calls
- Calls nested under the trace that triggered them

{{ before_you_start() }}

## Installation

Install `logfire` with the `botocore` extra:

{{ install_logfire(extras=['botocore']) }}

## Usage

Call [`logfire.instrument_botocore()`][logfire.Logfire.instrument_botocore] after configuring
Logfire and before creating or using a botocore or Boto3 client:

```python skip-run="true" skip-reason="external-connection"
import boto3

import logfire

logfire.configure()
logfire.instrument_botocore()

s3 = boto3.client('s3')
s3.list_buckets()
```

The method also accepts callbacks that let you add application-specific information to each span.
OpenTelemetry (OTel) is the open industry standard for collecting traces, metrics, and logs;
anything OpenTelemetry-compatible works with Logfire. OTel calls `request_hook` with the span,
service name, operation name, and API parameters. It calls `response_hook` with the span, service
name, operation name, and result:

```python
from typing import Any

from opentelemetry.trace import Span

import logfire


def request_hook(span: Span, service_name: str, operation_name: str, api_params: dict[str, Any]) -> None:
    span.set_attribute('app.aws_operation', f'{service_name}.{operation_name}')


def response_hook(span: Span, service_name: str, operation_name: str, result: Any) -> None:
    span.set_attribute('app.aws_response_received', result is not None)


logfire.configure()
logfire.instrument_botocore(request_hook=request_hook, response_hook=response_hook)
```

## Verify it worked

Make an AWS API call, then open the [Live view](../guides/web-ui/live.md). Within a few seconds,
you'll see a span named for the AWS service and operation, such as `S3.ListBuckets`.

## Troubleshooting

- **No AWS spans appear:** Call `logfire.configure()` and `logfire.instrument_botocore()` before
  creating or using the client, and call `instrument_botocore()` only once.
- **The botocore integration is missing:** Install `logfire[botocore]`, which includes
  `opentelemetry-instrumentation-botocore` version 0.65b0 or later.
- **Boto3 calls are not recorded:** Boto3 uses botocore internally, so the same instrumentation
  applies. Check that the client was not used before instrumentation was enabled.

## Reference

- [`logfire.instrument_botocore()`][logfire.Logfire.instrument_botocore]: the Logfire API reference.
- [OpenTelemetry botocore instrumentation][opentelemetry-botocore]: the underlying package and hook signatures.

[opentelemetry-botocore]: https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/botocore/botocore.html
