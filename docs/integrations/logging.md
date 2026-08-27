---
title: "Send standard library logs to Logfire"
description: "Route the logs from Python's built-in logging module into Logfire, so your existing log output shows up alongside your traces with no change to how you log."
integration: logfire
---
# Standard library logging

Attach Logfire to Python's built-in [logging](https://docs.python.org/3/library/logging.html) module and your existing log output shows up in
Logfire as structured **logs** (individual timestamped records of something that happened), next to
the **traces** (the full journey of one request through your app) from the rest of your code. Every
message written through the standard `logging` module (including logs from third-party libraries
that use it) becomes a Logfire log, with no change to how you call `logger.info(...)` and friends.

## What you'll capture

- Each standard-library log message
- Its severity level (debug, info, warning, error, and so on)
- Its timestamp
- The logger name and any structured fields attached to the record

{{ before_you_start() }}

## Installation

Install `logfire`:

{{ install_logfire() }}

No extra library needed: this works with Python's built-in `logging` module.

## Usage

Call `logfire.configure()` to connect to your project, then attach
[`LogfireLoggingHandler`][logfire.LogfireLoggingHandler] to your logging configuration so every log
record is also sent to Logfire. You can wire it up with either
[`basicConfig()`][logging.basicConfig] or [`dictConfig()`][logging.config.dictConfig]:

=== "Using [`basicConfig()`][logging.basicConfig]"

    ```py title="main.py" skip-run="true" skip-reason="global-state"
    from logging import basicConfig, getLogger

    import logfire

    logfire.configure()
    basicConfig(handlers=[logfire.LogfireLoggingHandler()])

    logger = getLogger(__name__)

    logger.error('Hello %s!', 'Fred')
    # 10:05:06.855 Hello Fred!
    ```

=== "Using [`dictConfig()`][logging.config.dictConfig]"

    ```py title="main.py" skip-run="true" skip-reason="global-state"
    from logging import getLogger
    from logging.config import dictConfig

    import logfire

    logfire.configure()
    dictConfig(
        {
            'version': 1,
            'handlers': {
                'logfire': {
                    'class': 'logfire.LogfireLoggingHandler',
                },
            },
            'root': {
                'handlers': ['logfire'],
            },
        }
    )

    logger = getLogger(__name__)

    logger.error('Hello %s!', 'Fred')
    # 10:05:06.855 Hello Fred!
    ```

The [`LogfireLoggingHandler`][logfire.LogfireLoggingHandler] will emit log records to the Logfire instance,
unless [instrumentation is suppressed](../how-to-guides/suppress.md#suppress-instrumentation), in which case
a [fallback][logfire.LogfireLoggingHandler(fallback)] handler will be used (defaults to
[`StreamHandler`][logging.StreamHandler], writing to [`sys.stderr`][]).

## Verify it worked

Run your program, then open the [Live view](../guides/web-ui/live.md) in the Logfire web app.
Within a few seconds you'll see your message as a record.

## Advanced

### Quiet a noisy logger

Logging can be too verbose, especially from third-party libraries.
You can raise a logger's level to suppress logs that are less important.
Let's see an example with the [`apscheduler`](https://apscheduler.readthedocs.io/en/stable/) logger:

```py title="main.py"
import logging

logger = logging.getLogger('apscheduler')
logger.setLevel(logging.WARNING)
```

In this example, we set the log level of the `apscheduler` logger to `WARNING`, which means that
only logs with a level of `WARNING` or higher will be emitted.

### Disabling `urllib3` debug logs

As instrumentation is suppressed when sending log data to **Logfire**, unexpected [`DEBUG`][logging.DEBUG] logs
can appear in the console (through the use of the [fallback][logfire.LogfireLoggingHandler(fallback)] handler),
emitted when performing the API request to send logs.

To disable such logs, a [filter](https://docs.python.org/3/library/logging.html#filter-objects) can be used:

=== "Using [`basicConfig()`][logging.basicConfig]"

    ```py title="main.py" skip-run="true" skip-reason="global-state"
    import logging
    from logging import DEBUG, basicConfig

    import logfire

    logfire.configure()
    logfire_handler = logfire.LogfireLoggingHandler()

    urllib3_filter = logging.Filter('urllib3')
    # Disable urllib3 debug logs on the fallback handler
    # (by default, writing to `sys.stderr`):
    logfire_handler.fallback.addFilter(lambda record: not urllib3_filter.filter(record))

    basicConfig(handlers=[logfire_handler], level=DEBUG)
    ```

=== "Using [`dictConfig()`][logging.config.dictConfig]"

    ```py title="main.py" skip-run="true" skip-reason="global-state"
    import logging
    from logging.config import dictConfig

    import logfire

    logfire.configure()

    fallback = logging.StreamHandler()

    urllib3_filter = logging.Filter('urllib3')
    # Disable urllib3 debug logs on the fallback handler
    # (by default, writing to `sys.stderr`):
    fallback.addFilter(lambda record: not urllib3_filter.filter(record))

    dictConfig(
        {
            'version': 1,
            'disable_existing_loggers': False,
            'handlers': {
                'logfire': {
                    'class': 'logfire.LogfireLoggingHandler',
                    'level': 'DEBUG',
                    'fallback': fallback,
                },
            },
            'root': {
                'handlers': ['logfire'],
                'level': 'DEBUG',
            },
        }
    )
    ```

## Troubleshooting

Not seeing your logs in Logfire? Check that `logfire.configure()` ran first, your write token is set,
and the `LogfireLoggingHandler` is attached to your logging configuration (via `basicConfig()`,
`dictConfig()`, or added to the relevant logger).

## Reference

- API reference: [`logfire.LogfireLoggingHandler`][logfire.LogfireLoggingHandler]
