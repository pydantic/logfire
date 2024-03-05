# [Standard Library Logging][logging]

Logfire can act as a sink for standard library logging by emitting a Logfire log for every standard library log record.

```py title="main.py"
from logging import basicConfig, getLogger

from logfire.integrations.logging import LogfireLoggingHandler

basicConfig(handlers=[LogfireLoggingHandler()])

logger = getLogger(__name__)

logger.error("Hello %s!", "Fred")
#> 2021-08-25 15:00:00,000 [ERROR] main.py:7: Hello Fred!
```

[logging]: https://docs.python.org/3/library/logging.html
