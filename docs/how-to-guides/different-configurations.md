Sometimes you need different Logfire configurations for different parts of your application. You can do this with [`logfire.configure(local=True, ...)`][logfire.configure(local)].

For example, here's how to disable console logging for database operations while keeping it enabled for other parts:

```python
import logfire

# Global configuration is the default and should generally only be done once:
logfire.configure()

# Locally configured instance without console logging
no_console_logfire = logfire.configure(local=True, console=False)

# Simple demonstration:
logfire.info('This uses the global config and will appear in the console')
no_console_logfire.info('This uses the local config and will NOT appear in the console')

# Calling functions on the `logfire` module will use the global configuration
# This will send spans about HTTP requests to both Logfire and the console
logfire.instrument_httpx()

# This will send spans about DB queries to Logfire but not to the console
no_console_logfire.instrument_psycopg()
```
