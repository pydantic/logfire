# Alternative backends

**Logfire** uses the OpenTelemetry standard. This means that you can configure the SDK to export to any backend that supports OpenTelemetry.

The easiest way is to set the `OTEL_EXPORTER_OTLP_ENDPOINT` environment variable to a URL that points to your backend.
This will be used as a base, and the SDK will append `/v1/traces` and `/v1/metrics` to the URL to send traces and metrics, respectively.

Alternatively, you can use the `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT` and `OTEL_EXPORTER_OTLP_METRICS_ENDPOINT` environment variables to specify the URLs for traces and metrics separately. These URLs should include the full path, including `/v1/traces` and `/v1/metrics`.

!!! note
    The data can be encoded using either **Protobuf** or **JSON** and sent over **HTTP** (not gRPC).

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

## Other environment variables

If `OTEL_TRACES_EXPORTER` and/or `OTEL_METRICS_EXPORTER` are set to any non-empty value other than `otlp`, then **Logfire** will ignore the corresponding `OTEL_EXPORTER_OTLP_*` variables. This is because **Logfire** doesn't support other exporters, so we assume that the environment variables are intended to be used by something else. Normally you don't need to worry about this, and you don't need to set these variables at all unless you want to prevent **Logfire** from setting up these exporters.

See the [OpenTelemetry documentation](https://opentelemetry-python.readthedocs.io/en/latest/exporter/otlp/otlp.html) for information about the other headers you can set, such as `OTEL_EXPORTER_OTLP_HEADERS`.
