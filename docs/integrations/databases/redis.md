---
title: "Instrument Redis: see every command your app runs"
description: "Add a few lines to your Redis code and see every command in Logfire: which command ran, how long it took, and which ones failed."
integration: otel
---
# Redis

See every command your app sends to [Redis][redis] (which command ran, how long it took, and which
ones failed) as a **span** (one unit of work with a name, a start, and a duration) in Logfire.
Related spans link together into a **trace** (the full journey of one request), so a slow lookup shows
up right next to the code that triggered it.

## What you'll capture

- Each command as a span, with its duration and any errors
- Which Redis server the command went to
- Optionally, the command itself (off by default; see below)

{{ before_you_start() }}

## Installation

Install `logfire` with the `redis` extra:

{{ install_logfire(extras=['redis']) }}

## Usage

Add two lines to your app: `logfire.configure()` to connect to your project, and
[`logfire.instrument_redis()`][logfire.Logfire.instrument_redis] to record every command.

The example below connects to a local Redis server. If you don't have one running, you can start one
with Docker:

```bash
docker run --name redis -p 127.0.0.1:6379:6379 -d redis:latest
```

```py title="main.py" hl_lines="6" skip-run="true" skip-reason="external-connection"
import redis

import logfire

logfire.configure()
logfire.instrument_redis()

client = redis.StrictRedis(host='localhost', port=6379)
client.set('my-key', 'my-value')


async def main():
    client = redis.asyncio.Redis(host='localhost', port=6379)
    await client.get('my-key')


if __name__ == '__main__':
    import asyncio

    asyncio.run(main())
```

Run it with `python main.py`.

## Verify it worked

Run your program, then open your project in the
[Logfire web app](https://logfire.pydantic.dev/) and go to the **Live** view. Within a few seconds you
should see a span for each command the script ran. Click one to see how long it took.

## Troubleshooting

Not seeing your commands in Logfire? Check these first:

- **`logfire.configure()` runs before `logfire.instrument_redis()`.** Configure the connection first,
  then instrument.
- **You call `instrument_redis()` exactly once.**
- **Your write token is set.** In local development, run `logfire projects use <your-project>`; in
  production, set the `LOGFIRE_TOKEN` environment variable. See [Getting Started](../../index.md).
- **You actually ran a command.** Spans appear only after a command executes.

## Advanced

### Capturing the command

By default, the command sent to Redis isn't recorded, since it can contain sensitive data. To include
it, pass `capture_statement=True`:

```py skip-run="true" skip-reason="external-connection"
import logfire

logfire.configure()
logfire.instrument_redis(capture_statement=True)
```

Turning this on sends the command (including any values in it) to Logfire, so avoid it if your
commands carry secrets or personally identifiable information (PII).

### Passing options to the OpenTelemetry instrumentor

[`logfire.instrument_redis()`][logfire.Logfire.instrument_redis] accepts additional keyword arguments
and passes them to the OpenTelemetry Redis instrumentation. See
[their documentation][opentelemetry-redis] for the full list.

## Reference

- Underlying OpenTelemetry package: [Redis instrumentation][opentelemetry-redis]

::: logfire.Logfire.instrument_redis
    options:
        heading_level: 4
        show_source: false
        show_root_doc_entry: true
        show_root_heading: true
        show_root_full_path: false

::: logfire.integrations.redis.RequestHook
    options:
        heading_level: 4
        show_root_heading: true
        show_root_full_path: false
        show_source: false
        filters: []

::: logfire.integrations.redis.ResponseHook
    options:
        heading_level: 4
        show_root_heading: true
        show_root_full_path: false
        show_source: false
        filters: []

[redis]: https://redis.readthedocs.io/en/stable/
[opentelemetry-redis]: https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/redis/redis.html
