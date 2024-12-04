# Alternative clients

**Logfire** uses the OpenTelemetry standard. This means that you can configure standard OpenTelemetry SDKs
in many languages to export to the **Logfire** backend. Depending on your SDK, you may need to set only
these [environment variables](https://opentelemetry.io/docs/languages/sdk-configuration/otlp-exporter/):

- `OTEL_EXPORTER_OTLP_ENDPOINT=https://logfire-api.pydantic.dev` for both traces and metrics, or:
    - `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=https://logfire-api.pydantic.dev/v1/traces` for just traces
    - `OTEL_EXPORTER_OTLP_METRICS_ENDPOINT=https://logfire-api.pydantic.dev/v1/metrics` for just metrics
- `OTEL_EXPORTER_OTLP_HEADERS='Authorization=your-write-token'` - see [Creating Write Tokens](./creating-write-tokens.md)
  to obtain a write token and replace `your-write-token` with it.
- `OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf` to export in Protobuf format over HTTP (not gRPC).
  The **Logfire** backend supports both Protobuf and JSON, but only over HTTP for now. Some SDKs (such as Python) already use this value as the default so setting this isn't required, but other SDKs use `grpc` as the default.

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

## Example with NodeJS

Create these files:

```json title="package.json"
{
  "type": "module",
  "dependencies": {
    "@opentelemetry/sdk-node": "*"
  }
}
```

```js title="main.js"
import {NodeSDK} from "@opentelemetry/sdk-node";
import {OTLPTraceExporter} from "@opentelemetry/exporter-trace-otlp-proto";
import {BatchSpanProcessor} from "@opentelemetry/sdk-trace-node";
import {trace} from "@opentelemetry/api";
import {Resource} from "@opentelemetry/resources";
import {ATTR_SERVICE_NAME} from "@opentelemetry/semantic-conventions";

const traceExporter = new OTLPTraceExporter();
const spanProcessor = new BatchSpanProcessor(traceExporter);
const resource = new Resource({[ATTR_SERVICE_NAME]: "my_service"});
const sdk = new NodeSDK({spanProcessor, resource});
sdk.start();

const tracer = trace.getTracer("my_tracer");
tracer.startSpan("Hello World").end();

sdk.shutdown().catch(console.error);
```

Then run these commands:

```sh
export OTEL_EXPORTER_OTLP_ENDPOINT=https://logfire-api.pydantic.dev
export OTEL_EXPORTER_OTLP_HEADERS='Authorization=your-write-token'

npm install
node main.js
```

## Example with Rust

First, set up a new Cargo project:

```sh
cargo new --bin otel-example && cd otel-example
export OTEL_EXPORTER_OTLP_ENDPOINT=https://logfire-api.pydantic.dev
export OTEL_EXPORTER_OTLP_HEADERS='Authorization=your-write-token'
```

Update the `Cargo.toml` and `main.rs` files with the following contents:

```toml title="Cargo.toml"
[package]
name = "otel-example"
version = "0.1.0"
edition = "2021"

[dependencies]
opentelemetry = { version = "*", default-features = false, features = ["trace"] }
# Note: `reqwest-rustls` feature is necessary else you'll have a cryptic failure to export;
# see https://github.com/open-telemetry/opentelemetry-rust/issues/2169
opentelemetry-otlp = { version = "*", default-features = false, features = ["trace", "http-proto", "reqwest-blocking-client", "reqwest-rustls"] }
```

```rust title="src/main.rs"
use opentelemetry::{
    global::ObjectSafeSpan,
    trace::{Tracer, TracerProvider},
};

fn main() -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
    let otlp_exporter = opentelemetry_otlp::new_exporter()
        .http()
        .with_protocol(opentelemetry_otlp::Protocol::HttpBinary)
        // If you don't want to export environment variables, you can also configure
        // programmatically like so:
        //
        // (You'll need to add `use opentelemetry_otlp::WithExportConfig;` to the top of the
        // file to access the `.with_endpoint` method.)
        //
        // .with_endpoint("https://logfire-api.pydantic.dev/v1/traces")
        // .with_headers({
        //     let mut headers = std::collections::HashMap::new();
        //     headers.insert(
        //         "Authorization".into(),
        //         "your-write-token".into(),
        //     );
        //     headers
        // })
        ;

    let tracer_provider = opentelemetry_otlp::new_pipeline()
        .tracing()
        .with_exporter(otlp_exporter)
        .install_simple()?;
    let tracer = tracer_provider.tracer("my_tracer");

    tracer.span_builder("Hello World").start(&tracer).end();

    Ok(())
}

```

Finally, use `cargo run` to execute.

## Example with Go

Create a file `main.go` containing the following:

```go
package main

import (
    "context"
    "go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracehttp"
    "go.opentelemetry.io/otel/sdk/trace"
)

func main() {
    ctx := context.Background()
    traceExporter, _ := otlptracehttp.New(ctx)
    batchSpanProcessor := trace.NewBatchSpanProcessor(traceExporter)
    tracerProvider := trace.NewTracerProvider(trace.WithSpanProcessor(batchSpanProcessor))
    tracer := tracerProvider.Tracer("my_tracer")

    ctx, span := tracer.Start(ctx, "Hello World")
    span.End()

    tracerProvider.Shutdown(ctx)
}
```

Then run these commands:

```sh
export OTEL_EXPORTER_OTLP_ENDPOINT=https://logfire-api.pydantic.dev
export OTEL_EXPORTER_OTLP_HEADERS='Authorization=your-write-token'

# Optional, but otherwise you will see the service name set to `unknown_service:otel_example`
export OTEL_RESOURCE_ATTRIBUTES="service.name=my_service"

go mod init otel_example
go mod tidy
go run .
```
