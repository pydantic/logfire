---
integration: logfire
---

# Standard Library Logging

**Logfire** can act as a sink for [standard library logging][logging] by emitting a **Logfire** log for
every standard library log record.

=== "Using [`basicConfig()`][logging.basicConfig]"

    ```py title="main.py"
    from logging import basicConfig, getLogger

    import logfire

    logfire.configure()
    basicConfig(handlers=[logfire.LogfireLoggingHandler()])

    logger = getLogger(__name__)

    logger.error("Hello %s!", "Fred")
    # 10:05:06.855 Hello Fred!
    ```

=== "Using [`dictConfig()`][logging.config.dictConfig]"

    ```py title="main.py"
    from logging.config import dictConfig

    import logfire

    logfire.configure()
    dictConfig({
        'version': 1,
        'handlers': {
            'logfire': {
                'class': 'logfire.LogfireLoggingHandler',
            },
        },
        'root': {
            'handlers': ['logfire'],
        },
    })

    logger = getLogger(__name__)

    logger.error("Hello %s!", "Fred")
    # 10:05:06.855 Hello Fred!
    ```

The [`LogfireLoggingHandler`][logfire.LogfireLoggingHandler] will emit log records to the Logfire instance,
unless [instrumentation is suppressed](../how-to-guides/suppress.md#suppress-instrumentation), in which case
a [fallback][logfire.LogfireLoggingHandler(fallback)] handler will be used (defaults to
[`StreamHandler`][logging.StreamHandler], writing to [`sys.stderr`][]).

## Oh no! Too many logs from...

A common issue with logging is that it can be **too verbose**... Right? :sweat_smile:

Don't worry! We are here to help you.

In those cases, you can set the log level to a higher value to suppress logs that are less important.
Let's see an example with the [`apscheduler`](https://apscheduler.readthedocs.io/en/stable/) logger:

```py title="main.py"
import logging

logger = logging.getLogger("apscheduler")
logger.setLevel(logging.WARNING)
```

In this example, we set the log level of the `apscheduler` logger to `WARNING`, which means that
only logs with a level of `WARNING` or higher will be emitted.

## Disabling `urllib3` debug logs

As instrumentation is suppressed when sending log data to **Logfire**, unexpected [`DEBUG`][logging.DEBUG] logs
can appear in the console (through the use of the [fallback][logfire.LogfireLoggingHandler(fallback)] handler),
emitted when performing the API request to send logs.

To disable such logs, a [filter](https://docs.python.org/3/library/logging.html#filter-objects) can be used:

=== "Using [`basicConfig()`][logging.basicConfig]"

    ```py title="main.py"
    import logging
    from logging import DEBUG, basicConfig, getLogger

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

    ```py title="main.py"
    import logging
    from logging.config import dictConfig

    import logfire

    logfire.configure()

    fallback = logging.StreamHandler()

    urllib3_filter = logging.Filter('urllib3')
    # Disable urllib3 debug logs on the fallback handler
    # (by default, writing to `sys.stderr`):
    fallback.addFilter(lambda record: not urllib3_filter.filter(record))

    dictConfig({
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
    })
    ```
