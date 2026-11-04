---
title: "Trace Valkey commands with Logfire"
description: "See which commands your Python Valkey clients ran, how long they took, and which ones failed."
integration: otel
---
# Valkey

See commands your Python clients send to [Valkey][valkey] (which command ran, how long it took, and which
ones failed) as a **span** (one unit of work with a name, a start, and a duration) in Logfire.
Related spans link together into a **trace** (the full journey of one request), so a slow lookup shows
up right next to the code that triggered it.

[Valkey](https://valkey.io/) is an open source fork of Redis. Its Python client
([`valkey-py`](https://valkey-py.readthedocs.io/en/stable/)) is API-compatible with `redis-py`,
but the OpenTelemetry Redis instrumentation only patches the `redis` package, so Valkey commands
need their own instrumentation.

## What you'll capture

- Each command executed by a synchronous or asynchronous Valkey client, with its duration and any errors
- The server address and port when the client provides them
- The command name by default, with its arguments hidden

When Valkey returns an error, the span records its type. Server error messages can contain command
arguments, so the span omits those messages.

{{ before_you_start() }}

## Installation

Install Logfire with the `valkey` extra. The integration requires `valkey` 6.0 or later.

{{ install_logfire(extras=['valkey']) }}

## Usage

Add two lines to your app: `logfire.configure()` to connect to your project, and
[`logfire.instrument_valkey()`][logfire.Logfire.instrument_valkey] to record commands. The first call sets the options for the whole process and applies to
clients you already created. Pipelines, cluster clients, and publish/subscribe commands are outside
the scope of this integration.

The example below connects to a local Valkey server. If you don't have one running, you can start one
with Docker:

```bash
docker run --name valkey -p 127.0.0.1:6379:6379 -d valkey/valkey:latest
```

```py title="main.py" hl_lines="4 5" skip-run="true" skip-reason="external-connection"
import logfire
import valkey

logfire.configure()
logfire.instrument_valkey()

with valkey.Valkey(host='localhost', port=6379) as client:
    client.set('my-key', 'my-value')
    client.get('my-key')
```

Run it with `python main.py`.

## Verify it worked

Run your program, then open your project in the
[Logfire web app](https://logfire.pydantic.dev/) and go to the **Live** view. Within a few seconds you
should see a `SET` span and a `GET` span. The `SET` span displays `SET ? ?`. Click it to see
how long the command took.

## Troubleshooting

Not seeing your commands in Logfire? Check these first:

- **`logfire.configure()` runs before `logfire.instrument_valkey()`.** Configure the connection first,
  then instrument.
- **Your write token is set.** In local development, run `logfire projects use <your-project>`; in
  production, set the `LOGFIRE_TOKEN` environment variable. See [Getting Started](../../index.md).
- **You actually ran a command.** Spans appear only after a command executes.
- **You're using the `valkey` package, not `redis`.** Use `instrument_valkey()` for `valkey-py` and
  [`instrument_redis()`](./redis.md) for `redis-py`.

## Advanced

`logfire run` instruments Valkey with the default settings when it finds the `valkey` package.
If your application sets custom options, run it with `logfire run --exclude valkey` and let the
application call `logfire.instrument_valkey()`.

### Capturing the command

Logfire replaces each argument with `?` in the span message and `db.statement` attribute. To
include arguments in a separate `db.valkey.command` attribute, pass `capture_statement=True`.

```py skip-run="true" skip-reason="external-connection"
import logfire

logfire.configure()
logfire.instrument_valkey(capture_statement=True)
```

Logfire applies its [scrubbing rules](../../how-to-guides/scrubbing.md) to that attribute and
always omits it for `ACL`, `AUTH`, `CONFIG`, `HELLO`, and `MIGRATE`. Enable capture only when
your command arguments are suitable to send to Logfire.

## Reference

::: logfire.Logfire.instrument_valkey
    options:
        heading_level: 4
        show_source: false
        show_root_doc_entry: true
        show_root_heading: true
        show_root_full_path: false

::: logfire.integrations.valkey.RequestHookContext
    options:
        heading_level: 4
        show_root_heading: true
        show_root_full_path: false
        show_source: false
        filters: []

::: logfire.integrations.valkey.ResponseHookContext
    options:
        heading_level: 4
        show_root_heading: true
        show_root_full_path: false
        show_source: false
        filters: []

[valkey]: https://valkey.io/
