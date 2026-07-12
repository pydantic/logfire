---
title: "Instrument FastStream: trace messages through your brokers"
description: "Add FastStream's OpenTelemetry middleware to see messages flow through your brokers as traces in Logfire."
integration: "built-in"
---
# FastStream

See every message your [FastStream][faststream] app publishes and consumes: which channel it went
to, how long handling took, and whether it failed, as a **span** (one unit of work with a name, a
start, and a duration) in Logfire. Spans link together into a **trace** (the full journey of one
message), so you can follow a message from where it was published to where it was handled.

FastStream ships its own OpenTelemetry middleware: a small piece that wraps each broker to record
this. So instead of a `logfire.instrument_*` call, you add FastStream's middleware for your broker;
Logfire receives what it emits.

## What you'll capture

- Each published and consumed message as a span, with its duration and status
- The channel or subject the message went to
- Failed message handling, with the error

## Before you start

You'll need a Logfire project and its **write token**: the credential your app uses to send data to
Logfire. Create a project and copy its token from **Project → Settings → Write tokens** in the
Logfire web app. New to Logfire? Start with [Getting Started](../../index.md), which walks through
creating a project and linking your machine.

## Installation

FastStream has no separate Logfire extra: the OpenTelemetry support lives in FastStream itself. Just
install `logfire`:

{{ install_logfire() }}

## Usage

Two steps:

1. Call `logfire.configure()` to connect to your project.
2. Add FastStream's OpenTelemetry middleware for your broker.

The example below uses Redis, so it adds the
[`RedisTelemetryMiddleware`][faststream.redis.opentelemetry.RedisTelemetryMiddleware]. If you use a
different broker, add that broker's matching middleware instead.

```python title="main.py" hl_lines="7 11" skip-run="true" skip-reason="external-connection"
from faststream import FastStream
from faststream.redis import RedisBroker
from faststream.redis.opentelemetry import RedisTelemetryMiddleware

import logfire

logfire.configure()

broker = RedisBroker(middlewares=(RedisTelemetryMiddleware(),))

app = FastStream(broker)


@broker.subscriber('test-channel')
@broker.publisher('another-channel')
async def handle():
    return 'Hi!'


@broker.subscriber('another-channel')
async def handle_next(msg: str):
    assert msg == 'Hi!'


@app.after_startup
async def test():
    await broker.publish('', channel='test-channel')
```

## Verify it worked

Run your app so it publishes a message, then open the [Live view](../../guides/web-ui/live.md). Within
a few seconds you'll see spans for the published and consumed messages: click one to see the channel
and how long handling took.

<!-- TODO(app-verify): screenshot of a FastStream message span in the Live view, showing the channel and duration -->

## Troubleshooting

Not seeing your messages? Check that `logfire.configure()` ran before your app started, that your
write token is set (run `logfire projects use <your-project>` locally, or set the `LOGFIRE_TOKEN`
environment variable in production; see [Getting Started](../../index.md)), and that you added the
telemetry middleware for the broker you're actually using.

## Reference

- [FastStream OpenTelemetry integration][faststream-otel]: how FastStream's middleware works, and the
  middleware for each broker.
- [FastStream documentation][faststream]: the project docs.

[faststream]: https://faststream.airt.ai/latest/
[faststream-otel]: https://faststream.airt.ai/latest/getting-started/opentelemetry/#faststream-tracing
