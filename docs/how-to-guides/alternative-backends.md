# Alternative backends

**Logfire** uses the OpenTelemetry standard. This means that you can configure the SDK to export to any backend that supports OpenTelemetry.

The easiest way is to set the `OTEL_EXPORTER_OTLP_ENDPOINT` environment variable to a URL that points to your backend.
This will be used as a base, and the SDK will append `/v1/traces` and `/v1/metrics` to the URL to send traces and metrics, respectively.

Alternatively, you can use the `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT`, `OTEL_EXPORTER_OTLP_METRICS_ENDPOINT` and `OTEL_EXPORTER_OTLP_LOGS_ENDPOINT`
environment variables to specify the URLs for traces, metrics and logs separately.
These URLs should include the full path, including `/v1/traces` and `/v1/metrics`.

!!! note
    The data will be encoded using **Protobuf** (not JSON) and sent over **HTTP** (not gRPC).

    Make sure that your backend supports this! :nerd_face:

## Example with Jaeger

Run this minimal command to start a [Jaeger](https://www.jaegertracing.io/) container:

```
docker run --rm \
  -p 16686:16686 \
  -p 4318:4318 \
  jaegertracing/all-in-one:latest
```

Then run this code:

```python
import os

import logfire

# Jaeger only supports traces, not metrics, so only set the traces endpoint
# to avoid errors about failing to export metrics.
# Use port 4318 for HTTP, not 4317 for gRPC.
traces_endpoint = 'http://localhost:4318/v1/traces'
os.environ['OTEL_EXPORTER_OTLP_TRACES_ENDPOINT'] = traces_endpoint

logfire.configure(
    # Setting a service name is good practice in general, but especially
    # important for Jaeger, otherwise spans will be labeled as 'unknown_service'
    service_name='my_logfire_service',

    # Sending to Logfire is on by default regardless of the OTEL env vars.
    # Keep this line here if you don't want to send to both Jaeger and Logfire.
    send_to_logfire=False,
)

with logfire.span('This is a span'):
    logfire.info('Logfire logs are also actually just spans!')
```

Finally open [http://localhost:16686/search?service=my_logfire_service](http://localhost:16686/search?service=my_logfire_service) to see the traces in the Jaeger UI.

## Example with Langfuse

Langfuse offers an [OpenTelemetry backend](https://langfuse.com/docs/opentelemetry/) that can receive trace data from Pydantic Logfire instrumentation to instrument your Pydantic AI agents.

First, set the required environment variables.

```python
import os
import base64

LANGFUSE_PUBLIC_KEY = "pk-lf-..."
LANGFUSE_SECRET_KEY = "sk-lf-..."
LANGFUSE_AUTH = base64.b64encode(f"{LANGFUSE_PUBLIC_KEY}:{LANGFUSE_SECRET_KEY}".encode()).decode()

os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"] = "https://cloud.langfuse.com/api/public/otel" # EU data region
# os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"] = "https://us.cloud.langfuse.com/api/public/otel" # US data region
os.environ["OTEL_EXPORTER_OTLP_HEADERS"] = f"Authorization=Basic {LANGFUSE_AUTH}"

# your openai key
os.environ["OPENAI_API_KEY"] = "sk-..."
```

Now, initialize Logfire’s instrumentation and define a sample Pydantic AI agent that makes use of dependency injection and tool registration. 

```python
import nest_asyncio
nest_asyncio.apply()
```

```python
import logfire

logfire.configure(
    service_name='my_logfire_service',

    # Sending to Logfire is on by default regardless of the OTEL env vars.
    send_to_logfire=False,
)
```

Make sure to pass `instrument=True` while configuring the `Agent`.

```python
from pydantic_ai import Agent, RunContext

roulette_agent = Agent(
    'openai:gpt-4o',
    deps_type=int,
    result_type=bool,
    system_prompt=(
        'Use the `roulette_wheel` function to see if the '
        'customer has won based on the number they provide.'
    ),
    instrument=True
)

@roulette_agent.tool
async def roulette_wheel(ctx: RunContext[int], square: int) -> str:
    """check if the square is a winner"""
    return 'winner' if square == ctx.deps else 'loser'
```

Finally, run your agent and generate trace data that will be sent to Langfuse. 

```python
# Run the agent
success_number = 18
result = roulette_agent.run_sync('Put my money on square eighteen', deps=success_number)
print(result.data)
```

You now can see the logs in Langfuse.

[Example trace in Langfuse](https://cloud.langfuse.com/project/cloramnkj0002jz088vzn1ja4/traces/01958b00f28af691900a70f06c3196e5?timestamp=2025-03-12T15%3A37%3A29.994Z&observation=a0a7ab9127ea620f)

![Pydantic AI OpenAI Trace](https://langfuse.com/images/cookbook/otel-integration-pydantic-ai/pydanticai-openai-trace-tree.png)

## Other environment variables

If `OTEL_TRACES_EXPORTER` and/or `OTEL_METRICS_EXPORTER` are set to any non-empty value other than `otlp`, then **Logfire** will ignore the corresponding `OTEL_EXPORTER_OTLP_*` variables. This is because **Logfire** doesn't support other exporters, so we assume that the environment variables are intended to be used by something else. Normally you don't need to worry about this, and you don't need to set these variables at all unless you want to prevent **Logfire** from setting up these exporters.

See the [OpenTelemetry documentation](https://opentelemetry-python.readthedocs.io/en/latest/exporter/otlp/otlp.html) for information about the other headers you can set, such as `OTEL_EXPORTER_OTLP_HEADERS`.
