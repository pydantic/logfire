# Loguru

**Logfire** can act as a sink for [Loguru][loguru] by emitting a **Logfire** log for every log record. For example:

```py title="main.py"
import logfire
from loguru import logger

logger.configure(handlers=[logfire.loguru_handler()])
logger.info('Hello, {name}!', name='World')
```

!!! note
    Currently, **Logfire** will not scrub sensitive data from the message formatted by Loguru, e.g:

    ```python
    logger.info('Foo: {bar}', bar='secret_value')
    # > 14:58:26.085 Foo: secret_value
    ```

[loguru]: https://github.com/Delgan/loguru
