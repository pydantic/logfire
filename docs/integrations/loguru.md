---
title: Pydantic Logfire Loguru Setup Guide
description: Seamlessly send all Loguru data to Logfire for analysis. Configure the specialized Loguru sink handler to centralize your logging data.
integration: logfire
---
# Loguru

**Logfire** can act as a sink for [Loguru][loguru] by emitting a **Logfire** log for every log record. For example:

```py title="main.py"
from loguru import logger

import logfire

logfire.configure()

logger.configure(handlers=[logfire.loguru_handler()])
logger.info('Hello, {name}!', name='World')
```

!!! note
    Currently, **Logfire** will not scrub sensitive data from the message formatted by Loguru, e.g:

    ```py skip="true" skip-reason="incomplete"
    logger.info('Foo: {bar}', bar='secret_value')
    # > 14:58:26.085 Foo: secret_value
    ```

[loguru]: https://github.com/Delgan/loguru
