# How to have different configurations for different instrumentations?

Sometimes you need different Logfire configurations for different parts of your application. For example, you want to disable console logging for database operations while keeping it enabled for other parts.

## Basic Example

Create a local configuration with different settings:

```python
import logfire

# Global configuration
logfire.configure()

# Local configuration without console logging
no_console_logfire = logfire.configure(local=True, console=False)

# Use the local configuration for psycopg
no_console_logfire.instrument_psycopg()

# Other instrumentations use the global configuration
logfire.instrument_httpx()
```

In this way, database operations won't appear in the console, while HTTP requests will still be logged to the console.
