# Structlog

**Logfire** has a built-in [structlog][structlog] processor that can be used to emit Logfire logs for every structlog event.

```py title="main.py" hl_lines="6 15"
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

The **Logfire** processor **MUST** come before the last processor that renders the logs in the structlog configuration.

By default, [`LogfireProcessor`][logfire.integrations.structlog.LogfireProcessor] shown above
disables console logging by logfire so you can use the existing logger you have configured for structlog, if you
want to log with logfire, use [`LogfireProcessor(console_log=True)`][logfire.integrations.structlog.LogfireProcessor].

!!! note
    Positional arguments aren't collected as attributes by the processor, since they are already part of the event
    message when the processor is called.

    If you have the following:

    ```py
    logger.error('Hello %s!', 'Fred')
    #> 2024-03-22 13:39:26 [error    ] Hello Fred!
    ```

    The string `'Fred'` will not be collected by the processor as an attribute, just formatted with the message.

[structlog]: https://www.structlog.org/en/stable/
