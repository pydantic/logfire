---
integration: logfire
---

# Standard Library Logging

**Logfire** can act as a sink for [standard library logging][logging] by emitting a **Logfire** log for
every standard library log record.

```py title="main.py"
from logging import basicConfig, getLogger

import logfire

logfire.configure()
basicConfig(handlers=[logfire.LogfireLoggingHandler()])

logger = getLogger(__name__)

logger.error("Hello %s!", "Fred")
# 10:05:06.855 Hello Fred!
```

## Oh no! Too many logs from...

A common issue with logging is that it can be **too verbose**... Right? :sweat_smile:

Don't worry! We are here to help you.

In those cases, you can set the log level to a higher value to suppress logs that are less important.
Let's see an example with the [`apscheduler`](https://apscheduler.readthedocs.io/en/3.x/) logger:

```py title="main.py"
import logging

logger = logging.getLogger("apscheduler")
logger.setLevel(logging.WARNING)
```

In this example, we set the log level of the `apscheduler` logger to `WARNING`, which means that
only logs with a level of `WARNING` or higher will be emitted.

[logging]: https://docs.python.org/3/library/logging.html
