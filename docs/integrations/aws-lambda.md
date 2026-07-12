---
title: "Instrument AWS Lambda: trace every function invocation"
description: "Add a call to instrument_aws_lambda and see each Lambda invocation in Logfire, with its duration, status, and any errors."
integration: otel
---
# AWS Lambda

See every invocation of your [AWS Lambda](https://aws.amazon.com/lambda/) function (how long it ran,
whether it succeeded, and any errors it raised) as a **trace** (the full journey of one invocation,
made of nested **spans**, where each span is one unit of work with a name, a start, and a duration) in
Logfire.

## What you'll capture

- Each invocation of your handler as a span, with its duration and status
- Any errors raised while the function ran
- Any instrumented work inside the handler (database queries, HTTP calls) as nested spans

## Before you start

You'll need a Logfire project and its **write token** (the key your app uses to send data). Create one
and copy it from **Project → Settings → Write tokens**. See [Getting Started](../index.md).

## Installation

Install `logfire` with the `aws-lambda` extra:

{{ install_logfire(extras=['aws-lambda']) }}

## Usage

Call `logfire.configure()` to connect to your project, then
[`logfire.instrument_aws_lambda()`][logfire.Logfire.instrument_aws_lambda] with your handler (after
the handler is defined) to record every invocation:

```python
import logfire

logfire.configure()  # (1)!


def handler(event, context):
    return 'Hello from Lambda'


logfire.instrument_aws_lambda(handler)
```

1. Set the `LOGFIRE_TOKEN` environment variable on your Lambda function's configuration in the AWS
   console so `configure()` can find your write token.

## Verify it worked

Invoke your function (for example, from the AWS console or with a test event), then open the
[Live view](../guides/web-ui/live.md). Within a few seconds you'll see a span for the invocation, with
its duration and status.

<!-- TODO(app-verify): screenshot of an AWS Lambda invocation span in the Live view, showing duration and status -->

## Troubleshooting

Not seeing your invocations in Logfire? Check that `logfire.configure()` ran before
`instrument_aws_lambda()`, that the `LOGFIRE_TOKEN` environment variable is set on the Lambda function's
configuration, and that you passed your handler to `instrument_aws_lambda()` exactly once.

## Reference

- [`logfire.instrument_aws_lambda()`][logfire.Logfire.instrument_aws_lambda]: the Logfire API reference.
- [OpenTelemetry AWS Lambda instrumentation][opentelemetry-aws-lambda]: the underlying package.

[opentelemetry-aws-lambda]: https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/aws_lambda/aws_lambda.html
