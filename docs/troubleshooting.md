---
title: "Troubleshooting Pydantic Logfire"
description: "Solutions for common issues when using Pydantic Logfire - missing data, configuration problems, and instrumentation troubleshooting."
---

# Troubleshooting

This guide covers common issues you might encounter when using Logfire and how to resolve them.

## No Data Appearing in Logfire

### Check that Logfire is configured

Make sure you've called `logfire.configure()` before creating any spans:

```python
import logfire

logfire.configure()  # Must be called before any instrumentation

# Now instrumentation will work
logfire.info("Hello, Logfire!")
```

### Check your project credentials

If you're using environment variables, verify they're set correctly:

```bash
echo $LOGFIRE_TOKEN
```

If you're using the CLI authentication, make sure you've run:

```bash
logfire auth
```

### Verify the send behavior

By default, Logfire only sends data when running in production-like environments. Check your `send_to_logfire` setting:

```python
import logfire

# Explicitly enable sending data
logfire.configure(send_to_logfire=True)
```

You can also set this via environment variable:

```bash
export LOGFIRE_SEND_TO_LOGFIRE=true
```

### Check for console output

Enable console output to verify spans are being created:

```python
import logfire

logfire.configure(console=logfire.ConsoleOptions(verbose=True))
```

If you see spans in the console but not in Logfire, the issue is with data export. If you don't see spans in the console either, the instrumentation isn't working.

---

## Instrumentation Not Working

### Auto-instrumentation must be called early

Instrumentation functions like `logfire.instrument_fastapi()` must be called before your application starts handling requests:

```python
import logfire
from fastapi import FastAPI

logfire.configure()

app = FastAPI()
logfire.instrument_fastapi(app)  # Call before adding routes

@app.get("/")
def root():
    return {"message": "Hello"}
```

### Check for conflicting OpenTelemetry configuration

If you have existing OpenTelemetry setup, Logfire might conflict with it. You can integrate Logfire with existing OTel configuration:

```python
import logfire
from opentelemetry import trace

# Get your existing provider
existing_provider = trace.get_tracer_provider()

# Configure Logfire to work alongside it
logfire.configure()
```

### Verify the package is instrumented

Some instrumentations require the underlying package to be installed:

```python
import logfire

# This will raise an error if httpx isn't installed
logfire.instrument_httpx()
```

Check that the package you're trying to instrument is installed in your environment.

---

## Missing Spans or Incomplete Traces

### Check sampling configuration

If you've configured sampling, some spans may be intentionally dropped:

```python
import logfire
from logfire.sampling import SamplingOptions

# Check if you have sampling configured
logfire.configure(
    sampling=SamplingOptions(
        head=0.1  # Only 10% of traces are captured
    )
)
```

### Async context not propagating

In async code, make sure context is properly propagated. Use `logfire.span` as a context manager:

```python
import logfire
import asyncio

async def my_task():
    with logfire.span("my_task"):
        await asyncio.sleep(1)
        logfire.info("Task completed")  # This will be part of the span
```

### Check for exceptions suppressing spans

If an exception occurs before a span is closed, the span might not be recorded properly. Use context managers:

```python
import logfire

# Good - span is always closed
with logfire.span("my_operation"):
    do_something()

# Risky - span might not close on exception
span = logfire.span("my_operation")
do_something()  # If this raises, span isn't closed
span.end()
```

---

## Configuration Issues

### Environment variables not being read

Logfire reads environment variables at configuration time. Make sure they're set before importing and configuring Logfire:

```bash
export LOGFIRE_TOKEN=your-token
python your_app.py
```

Common environment variables:

| Variable | Description |
|----------|-------------|
| `LOGFIRE_TOKEN` | Write token for authentication |
| `LOGFIRE_PROJECT_NAME` | Project name (defaults to directory name) |
| `LOGFIRE_SEND_TO_LOGFIRE` | Whether to send data (`true`/`false`) |
| `LOGFIRE_CONSOLE` | Console output options |
| `OTEL_SERVICE_NAME` | Service name for traces |

### Configuration file not found

Logfire looks for `pyproject.toml` or a `.logfire` directory. Verify your config file location:

```bash
# Check if pyproject.toml has logfire config
grep -A 10 "\[tool.logfire\]" pyproject.toml
```

### Multiple configure calls

Calling `logfire.configure()` multiple times can cause issues. Call it once at application startup:

```python
import logfire

# Do this once at startup
logfire.configure()

# Don't do this
# logfire.configure()  # Second call can cause issues
```

---

## Authentication Errors

### Token expired or invalid

If you see authentication errors, regenerate your token:

```bash
# Re-authenticate with the CLI
logfire auth

# Or create a new write token in the Logfire UI
# Settings > Write Tokens > Create Token
```

### Wrong project

Verify you're sending data to the correct project:

```python
import logfire

logfire.configure(
    token='your-write-token',  # Token is project-specific
)
```

---

## Performance Issues

### Too many spans being created

If your application is slow, you might be creating too many spans. Check for instrumentation in hot paths:

```python
import logfire

# Avoid instrumenting very frequent operations
for item in large_list:
    # Don't create a span for each item
    # with logfire.span("process_item"):  # Too many spans!
    process(item)

# Instead, instrument at a higher level
with logfire.span("process_all_items", item_count=len(large_list)):
    for item in large_list:
        process(item)
```

### Large attributes causing slowdown

Avoid attaching very large objects as span attributes:

```python
import logfire

# Avoid this - large payloads slow down export
with logfire.span("process", data=huge_object):
    pass

# Better - log a summary
with logfire.span("process", data_size=len(huge_object)):
    pass
```

---

## Getting More Help

If you're still experiencing issues:

1. **Enable debug logging** to see what Logfire is doing:
   ```python
   import logging
   logging.basicConfig(level=logging.DEBUG)
   ```

2. **Check the Logfire status page** for any ongoing incidents

3. **Search existing issues** on [GitHub](https://github.com/pydantic/logfire/issues)

4. **Ask in Slack** - the [Pydantic Logfire Slack](join-slack/index.html) community is very helpful

5. **Open a GitHub issue** with:
    - Your Logfire SDK version (`pip show logfire`)
    - Python version
    - Minimal code to reproduce the issue
    - Any error messages or logs

6. **Email support** at [engineering@pydantic.dev](mailto:engineering@pydantic.dev)

For self-hosted Logfire deployments, see the [Self-Hosted Troubleshooting](reference/self-hosted/troubleshooting.md) guide.
