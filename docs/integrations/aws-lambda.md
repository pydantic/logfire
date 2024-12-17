# AWS Lambda

The [`logfire.instrument_aws_lambda`][logfire.Logfire.instrument_aws_lambda] function can be used to
instrument AWS Lambda functions to automatically send traces to **Logfire**.

## Installation

Install `logfire` with the `aws-lambda` extra:

{{ install_logfire(extras=['aws-lambda']) }}

## Usage

To instrument an AWS Lambda function, call the `logfire.instrument_aws_lambda` function after defining
the handler function:

```python
import logfire

logfire.configure()  # (1)!


def handler(event, context):
    return 'Hello from Lambda'

logfire.instrument_aws_lambda(handler)
```

1. Remember to set the `LOGFIRE_TOKEN` environment variable on your Lambda function configuration.

[`logfire.instrument_aws_lambda`][logfire.Logfire.instrument_aws_lambda] uses the **OpenTelemetry AWS Lambda Instrumentation** package,
which you can find more information about [here][opentelemetry-aws-lambda].

[opentelemetry-aws-lambda]: https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/aws_lambda/aws_lambda.html
