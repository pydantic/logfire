---
title: "Instrument Valkey: see every command your app runs"
description: "Add a few lines to your Valkey code and see every command in Logfire: which command ran, how long it took, and which ones failed."
integration: otel
---
# Valkey

See every command your app sends to [Valkey][valkey] (which command ran, how long it took, and which
ones failed) as a **span** (one unit of work with a name, a start, and a duration) in Logfire.
Related spans link together into a **trace** (the full journey of one request), so a slow lookup shows
up right next to the code that triggered it.

[Valkey](https://valkey.io/) is an open source fork of Redis. Its Python client
([`valkey-py`](https://valkey-py.readthedocs.io/en/stable/)) is API-compatible with `redis-py`,
but the OpenTelemetry Redis instrumentation only patches the `redis` package, so Valkey commands
produce no spans unless you use `logfire.instrument_valkey()`.

## What you'll capture

- Each command as a span, with its duration and any errors
- Which Valkey server the command went to
- Optionally, the command itself (off by default; see below)

{{ before_you_start() }}

## Installation

Install `logfire` with the `valkey` extra:

{{ install_logfire(extras=['valkey']) }}

## Usage

Add two lines to your app: `logfire.configure()` to connect to your project, and
[`logfire.instrument_valkey()`][logfire.Logfire.instrument_valkey] to record every command.

The example below connects to a local Valkey server. If you don't have one running, you can start one
with Docker:

```bash
docker run --name valkey -p 127.0.0.1:6379:6379 -d valkey/valkey:latest
```

```py title="main.py" hl_lines="6" skip-run="true" skip-reason="external-connection"
import valkey

import logfire

logfire.configure()
logfire.instrument_valkey()

client = valkey.Valkey(host='localhost', port=6379)
client.set('my-key', 'my-value')


async def main():
    client = valkey.asyncio.Valkey(host='localhost', port=6379)
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

- **`logfire.configure()` runs before `logfire.instrument_valkey()`.** Configure the connection first,
  then instrument.
- **You call `instrument_valkey()` exactly once.**
- **Your write token is set.** In local development, run `logfire projects use <your-project>`; in
  production, set the `LOGFIRE_TOKEN` environment variable. See [Getting Started](../../index.md).
- **You actually ran a command.** Spans appear only after a command executes.
- **You're using the `valkey` package, not `redis`.** Use `instrument_valkey()` for `valkey-py` and
  [`instrument_redis()`](./redis.md) for `redis-py`.

## Advanced

### Capturing the command

By default, only the command name is recorded with argument values redacted as `?`
(e.g. `db.statement` = `SET ? ?`), since commands can contain sensitive data. To include
the full command with values, pass `capture_statement=True`:

```py skip-run="true" skip-reason="external-connection"
import logfire

logfire.configure()
logfire.instrument_valkey(capture_statement=True)
```

Turning this on sends the command (including any values in it) to Logfire, so avoid it if your
commands carry secrets or personally identifiable information (PII).

## Reference

::: logfire.Logfire.instrument_valkey
    options:
        heading_level: 4
        show_source: false
        show_root_doc_entry: true
        show_root_heading: true
        show_root_full_path: false

::: logfire.integrations.valkey.RequestHook
    options:
        heading_level: 4
        show_root_heading: true
        show_root_full_path: false
        show_source: false
        filters: []

::: logfire.integrations.valkey.ResponseHook
    options:
        heading_level: 4
        show_root_heading: true
        show_root_full_path: false
        show_source: false
        filters: []

[valkey]: https://valkey.io/
