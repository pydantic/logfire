---
title: "Send Structlog events to Logfire"
description: "Add Logfire's Structlog processor so every Structlog event also becomes a Logfire log."
integration: logfire
---
# Structlog

Add Logfire's [structlog][structlog] processor and your existing structlog output shows up in Logfire
as structured **logs** (individual timestamped records of something that happened), next to the
**traces** (the full journey of one request through your app) from the rest of your code. Every event
you already log, with all its structured fields, becomes a Logfire log.

## What you'll capture

- Each structlog event message
- Its severity level (info, warning, error, and so on)
- Its timestamp
- The structured key/value fields you attach to the event

{{ before_you_start() }}

## Installation

Install `logfire`:

{{ install_logfire() }}

This works with your existing `structlog` package: nothing extra to install. If you don't have it
yet, run `pip install structlog` in your terminal.

## Usage

Call `logfire.configure()` to connect to your project, then add
[`logfire.StructlogProcessor()`][logfire.integrations.structlog.LogfireProcessor] to your structlog
processor chain so every event is also sent to Logfire.

```py title="main.py" hl_lines="7 16"
from dataclasses import dataclass

import structlog

import logfire

logfire.configure()

structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.StackInfoRenderer(),
        structlog.dev.set_exc_info,
        structlog.processors.TimeStamper(fmt='%Y-%m-%d %H:%M:%S', utc=False),
        logfire.StructlogProcessor(),
        structlog.dev.ConsoleRenderer(),
    ],
)
logger = structlog.get_logger()


@dataclass
class User:
    id: int
    name: str


logger.info('Login', user=User(id=42, name='Fred'))
#> 2024-03-22 12:57:33 [info     ] Login                          user=User(id=42, name='Fred')
```

The Logfire processor **MUST** come before the last processor that renders the logs in the structlog
configuration.

## Verify it worked

Run your program, then open the [Live view](../guides/web-ui/live.md) in the Logfire web app.
Within a few seconds you'll see your event as a record, with its fields as attributes.

## Advanced

### Console logging

By default, [`LogfireProcessor`][logfire.integrations.structlog.LogfireProcessor] shown above
disables console logging by Logfire so you can use the existing logger you have configured for
structlog. If you want to log with Logfire's console output as well, use
[`LogfireProcessor(console_log=True)`][logfire.integrations.structlog.LogfireProcessor].

### Positional arguments

!!! note
    Positional arguments aren't collected as attributes by the processor, since they are already part
    of the event message when the processor is called.

    If you have the following:

    ```py skip="true" skip-reason="incomplete"
    logger.error('Hello %s!', 'Fred')
    #> 2024-03-22 13:39:26 [error    ] Hello Fred!
    ```

    The string `'Fred'` will not be collected by the processor as an attribute, just formatted with
    the message.

## Troubleshooting

Not seeing your events in Logfire? Check that `logfire.configure()` ran first, your write token is
set, and `logfire.StructlogProcessor()` is in your processor chain before the final rendering
processor.

## Reference

- API reference: [`logfire.integrations.structlog.LogfireProcessor`][logfire.integrations.structlog.LogfireProcessor]

[structlog]: https://www.structlog.org/en/stable/
