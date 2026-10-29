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

{{ before_you_start() }}

## Installation

Install `logfire`:

{{ install_logfire() }}

This works with your existing `loguru` package: nothing extra to install. If you don't have it yet,
run `pip install loguru` in your terminal.

## Usage

Call `logfire.configure()` to connect to your project, then add
[`logfire.loguru_handler()`][logfire.loguru_handler] as a Loguru sink (a destination Loguru writes
each log to) so every record Loguru emits is also sent to Logfire.

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

## Advanced

### Keep Loguru's console output

Loguru prints to your terminal through its own default sink. `logger.configure(handlers=[...])`
replaces that sink, so your terminal shows Logfire's console format instead of Loguru's. To keep
Loguru's format, add the Logfire handler next to the default sink with `logger.add()`, and pass
`console_log=False` so Logfire doesn't print each message a second time:

```py title="main.py" hl_lines="7"
from loguru import logger

import logfire

logfire.configure()

logger.add(**logfire.loguru_handler(console_log=False))
logger.info('Hello, {name}!', name='World')
```

Your terminal shows each message once, in Loguru's format, and every log is still sent to Logfire:

```
2026-10-29 17:38:20.930 | INFO     | __main__:<module>:8 - Hello, World!
```

Logfire still prints everything else it records, such as your traces, to the console. This option only
controls whether Logfire prints Loguru's logs. It doesn't change the format of Logfire's own console output.

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
