---
title: "Track AWS API calls from Boto3"
description: "Record Boto3 API calls as spans in Logfire, including the service, operation, duration, and errors."
integration: otel
---
# Boto3

See which Amazon Web Services (AWS) calls your application makes with [Boto3][boto3], how long they
take, and whether they fail. Each API call becomes a **span** (one operation with a start and a
duration), nested in the **trace** (the journey of a request) that triggered it.

## What you'll capture

- The AWS service and operation, such as `S3.ListBuckets`
- The region, duration, and errors for each API call
- Model and token-usage attributes for supported Amazon Bedrock model calls

!!! note "AWS request details are sent to Logfire"
    Operation names, resource identifiers, and error details can be recorded as span attributes and
    stored in Logfire. Use [scrubbing](../how-to-guides/scrubbing.md) to redact sensitive values before
    they leave your application.

{{ before_you_start() }}

## Installation

Install `logfire` with the `botocore` extra:

{{ install_logfire(extras=['botocore']) }}

This extra installs the OpenTelemetry instrumentor, not Boto3 itself. If Boto3 isn't already a
project dependency, install it too:

```bash
uv add boto3
```

## Usage

Configure [AWS credentials][credentials] before running this example. For local development, you can
use an AWS CLI profile and select it with `AWS_PROFILE`. In a deployed application, use its AWS role.
The example needs permission to list S3 buckets and explicitly selects the `us-east-1` region.
Don't put AWS access keys in your source code.

Call [`logfire.instrument_botocore()`][logfire.Logfire.instrument_botocore] once, after
`logfire.configure()` and before making AWS API calls. Botocore is the library Boto3 uses to make
those calls, so the same integration covers both libraries.

```py title="main.py" hl_lines="8" skip-run="true" skip-reason="external-connection"
from contextlib import closing

import boto3

import logfire

logfire.configure()
logfire.instrument_botocore()

with closing(boto3.client('s3', region_name='us-east-1')) as s3:
    with logfire.span('List S3 buckets'):
        response = s3.list_buckets()
        print([bucket['Name'] for bucket in response['Buckets']])
```

Run it with `python main.py`. For CLI auto-instrumentation, remove the explicit
`instrument_botocore()` call and run `logfire run main.py`. The CLI enables this integration
automatically when the `botocore` extra is installed.

## Verify it worked

Open [Live view](../guides/web-ui/live.md) and look for `List S3 buckets`. Expand it to find a
`S3.ListBuckets` child span with the AWS service, operation, and region. A failed AWS API call records
an error on its span and still raises the original exception in your application.

## Amazon Bedrock

For supported Bedrock models, the upstream instrumentor adds `gen_ai.*` attributes to `Converse` and
`InvokeModel` spans, including the model and input/output token counts. Enable the same
`instrument_botocore()` integration before using your `bedrock-runtime` client.

If you enable message-content capture with
`OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=true`, prompts and responses are recorded as log
events through this Logfire instance. They can contain sensitive data; review your scrubbing policy
before sending them to a Logfire project.

## Troubleshooting

- **No AWS spans:** check that the `botocore` extra is installed in the environment running your app,
  and enable instrumentation before the first API call. Check that other Logfire spans reach Live
  view too, so you can distinguish an instrumentation problem from an export problem.
- **Credentials or permissions errors:** follow Boto3's [credentials guide][credentials] and check the
  AWS principal's permissions. Instrumentation doesn't grant access to AWS resources.
- **Upload or download spans lose their parent:** Boto3's `upload_file()` and `download_file()` use
  background threads. Install `opentelemetry-instrumentation-threading` with
  `uv add opentelemetry-instrumentation-threading`, then enable the [threading instrumentor][threading]
  before Botocore instrumentation:

  ```py
  from opentelemetry.instrumentation.threading import ThreadingInstrumentor

  import logfire

  logfire.configure()
  ThreadingInstrumentor().instrument()
  logfire.instrument_botocore()
  ```
- **Async clients aren't traced:** this integration covers synchronous Botocore clients. Aiobotocore
  has a [separate OpenTelemetry instrumentor][aiobotocore].

## Next steps

[Browse other integrations](index.md) to trace the rest of your application.

## Reference

[`instrument_botocore()`][logfire.Logfire.instrument_botocore] accepts keyword arguments supported by
[the OpenTelemetry Botocore instrumentor][otel], including `request_hook` and `response_hook`.

[boto3]: https://docs.aws.amazon.com/boto3/latest/index.html
[credentials]: https://docs.aws.amazon.com/boto3/latest/guide/credentials.html
[otel]: https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/botocore/botocore.html
[threading]: https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/threading/threading.html
[aiobotocore]: https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/aiobotocore/aiobotocore.html
