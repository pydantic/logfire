# Alternative clients

**Logfire** uses the OpenTelemetry standard. This means that you can configure standard OpenTelemetry SDKs in many languages to export to the **Logfire** backend.

## Required OpenTelemetry environment variables {#otel-env-vars}

In general, you'll need to set the following two environment variables regardless of what language you're using:

```sh
export OTEL_EXPORTER_OTLP_ENDPOINT=https://logfire-api.pydantic.dev
export OTEL_EXPORTER_OTLP_HEADERS='Authorization=<your-write-token>'
```

See [Creating Write Tokens](./creating-write-tokens.md) to obtain a write token and replace `<your-write-token>` with it.

There are a number of other available, see the [OpenTelemetry](https://opentelemetry.io/docs/languages/sdk-configuration/otlp-exporter/) documentation.

## Example with Python

First, install the required dependencies:

```sh
pip install opentelemetry-exporter-otlp
```

Set required OTel environment variables, [see above :point_up:](#otel-env-vars).

Then run this script with `python`:

```python title="main.py"
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

## Example with Rust

First, set up a new Cargo project:

```sh
cargo new --bin logfire-rust-example && cd logfire-rust-example
```

Update the `Cargo.toml` and `src/main.rs` files with the following contents:

```toml title="Cargo.toml"
[package]
name = "logfire-rust-example"
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

Set required OTel environment variables, [see above :point_up:](#otel-env-vars).

Finally, run

```bash
cargo run
```

to execute.

## Example with Go

First, set up a new Go project:

```sh
mkdir logfire-go-example && cd logfire-go-example
go mod init logfire-go-example
```

Update the `go.mod` to include the following:

```go
module logfire-go-example

go 1.23.2

require (
	go.opentelemetry.io/otel v1.30.0
	go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracehttp v1.30.0
	go.opentelemetry.io/otel/sdk v1.30.0
	go.opentelemetry.io/otel/trace v1.30.0
)
```

Install those dependencies with

```sh
go get .
```

Then create a `main.go` file with the following contents:

```go title="main.go"
package main

import (
	"context"
	"log"
	"time"

	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracehttp"
	sdktrace "go.opentelemetry.io/otel/sdk/trace"
	"go.opentelemetry.io/otel/trace"
)

func main() {
  // Initialize the OpenTelemetry tracing system
	shutdown := initTracer()

  // Ensure the tracer is shut down at the end of the program
	defer shutdown()

  // Create a tracer and context
	tracer := otel.Tracer("go-example")
	ctx := context.Background()

	// create a span with span name "hello world"
	ctx, span := tracer.Start(
		ctx,
		"hello world",
		trace.WithAttributes(attribute.String("string-attribute", "potato")),
	)

  // set the span to end when the function returns
	defer span.End()
}

func initTracer() func() {
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)

	// Set up a trace exporter
	traceExporter, err := otlptracehttp.New(ctx)
	if err != nil {
		log.Fatalf("failed to create HTTP exporter: %v", err)
	}

	// Register the trace exporter with a TracerProvider, using a batch
	// span processor to aggregate spans before export.
	batchSpanProcessor := sdktrace.NewBatchSpanProcessor(traceExporter)
	tracerProvider := sdktrace.NewTracerProvider(
		sdktrace.WithSampler(sdktrace.AlwaysSample()),
		sdktrace.WithSpanProcessor(batchSpanProcessor),
	)
	otel.SetTracerProvider(tracerProvider)

	return func() {
		// Shutdown will flush any remaining spans and shut down the exporter.
		err := tracerProvider.Shutdown(ctx)
		if err != nil {
			log.Fatalf("failed to shutdown TracerProvider: %v", err)
		}
		cancel()
	}
}
```

Set required OTel environment variables, [see above :point_up:](#otel-env-vars).

Finally, run

```bash
go run main.go
```

to execute.

There's a complete example in the [`/examples/go/hello-world`](https://github.com/pydantic/logfire/tree/main/examples/go/hello-world/){:target="_blank"} directory of the logfire SDK repository.
