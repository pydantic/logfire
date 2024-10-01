# Alternative clients

**Logfire** uses the OpenTelemetry standard. This means that you can configure standard OpenTelemetry SDKs in many languages to export to the **Logfire** backend. Depending on your SDK, you may need to set only these [environment variables](https://opentelemetry.io/docs/languages/sdk-configuration/otlp-exporter/):

- `OTEL_EXPORTER_OTLP_ENDPOINT=https://logfire-api.pydantic.dev` for both traces and metrics, or:
  - `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=https://logfire-api.pydantic.dev/v1/traces` for just traces
  - `OTEL_EXPORTER_OTLP_METRICS_ENDPOINT=https://logfire-api.pydantic.dev/v1/metrics` for just metrics
- `OTEL_EXPORTER_OTLP_HEADERS='Authorization=your-write-token'` - see [Creating Write Tokens](./creating-write-tokens.md) to obtain a write token and replace `your-write-token` with it.
- `OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf` to export in Protobuf format over HTTP (not gRPC). The **Logfire** backend supports both Protobuf and JSON, but only over HTTP for now. Some SDKs (such as Python) already use this value as the default so setting this isn't required, but other SDKs use `grpc` as the defult.

## Example with Python

First, run these commands:

```sh
pip install opentelemetry-exporter-otlp
export OTEL_EXPORTER_OTLP_ENDPOINT=https://logfire-api.pydantic.dev
export OTEL_EXPORTER_OTLP_HEADERS='Authorization=your-write-token'
```

Then run this script with `python`:

```python
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

exporter = OTLPSpanExporter()
span_processor = BatchSpanProcessor(exporter)
tracer_provider = TracerProvider()
tracer_provider.add_span_processor(span_processor)
tracer = tracer_provider.get_tracer('my_tracer')

tracer.start_span('Hello World').end()
```

Then navigate to the Live view for your project in your browser. You should see a trace with a single span named `Hello World`.

To configure the exporter without environment variables:

```python
exporter = OTLPSpanExporter(
    endpoint='https://logfire-api.pydantic.dev/v1/traces',
    headers={'Authorization': 'your-write-token'},
)
```
