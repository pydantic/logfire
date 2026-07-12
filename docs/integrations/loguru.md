---
title: "Send Loguru logs to Logfire"
description: "Use Logfire as a Loguru sink so every Loguru log record also shows up in Logfire."
integration: logfire
---
# Loguru

Point [Loguru][loguru] at Logfire and your existing Loguru output shows up in Logfire as structured
**logs** (individual timestamped records of something that happened), next to the **traces** (the full
journey of one request through your app) from the rest of your code, with no change to how you write log
calls.

## What you'll capture

- Each Loguru log message
- Its severity level (info, warning, error, and so on)
- Its timestamp
- Any structured fields you attach to the record

## Before you start

You'll need a Logfire project and its **write token**: the credential your app uses to send data to
Logfire. Copy it from **Project → Settings → Write tokens** in the Logfire web app. New to Logfire?
Start with [Getting Started](../index.md).

## Installation

Install `logfire`:

{{ install_logfire() }}

This works with your existing `loguru` package: nothing extra to install. If you don't have it yet,
run `pip install loguru` in your terminal.

## Usage

Call `logfire.configure()` to connect to your project, then add
[`logfire.loguru_handler()`][logfire.loguru_handler] as a Loguru sink so every record Loguru
emits is also sent to Logfire.

```py title="main.py"
from loguru import logger

import logfire

logfire.configure()

logger.configure(handlers=[logfire.loguru_handler()])
logger.info('Hello, {name}!', name='World')
```

## Verify it worked

Run your program, then open the [Live view](../guides/web-ui/live.md) in the Logfire web app.
Within a few seconds you'll see your message as a record.

<!-- TODO(app-verify): screenshot of the log record in the Live view -->

## Advanced

### Scrubbing

!!! note
    Currently, **Logfire** will not scrub sensitive data from the message formatted by Loguru, e.g:

    ```py skip="true" skip-reason="incomplete"
    logger.info('Foo: {bar}', bar='secret_value')
    # > 14:58:26.085 Foo: secret_value
    ```

## Troubleshooting

Not seeing your logs in Logfire? Check that `logfire.configure()` ran first, your write token is set,
and the Logfire handler is attached to Loguru via `logger.configure(handlers=[...])`.

## Reference

- API reference: [`logfire.loguru_handler()`][logfire.loguru_handler]

[loguru]: https://github.com/Delgan/loguru
