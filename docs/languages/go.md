---
title: "Send traces from Go"
description: "Send traces from a Go application to Logfire using the standard OpenTelemetry SDK."
---

# Go

See what your Go application is doing in Logfire: the requests it handles, how long each one took, and which ones failed. This takes about five minutes.

Go does not have a dedicated Logfire SDK, but Logfire is built on [OpenTelemetry (OTel)](https://opentelemetry.io/), the open industry standard for collecting traces, metrics, and logs. The standard OpenTelemetry Go SDK sends data straight to Logfire once you point it at the right endpoint, and you get **traces** (the full journey of one request, made of nested **spans**, where a span is one unit of work with a name, a start, and a duration) in the Logfire UI.

## Before you start

You need:

- A Logfire project and a **write token** (the credential your app uses to send data to a Logfire project). Copy one from **Project → Settings → Write tokens**; see [Create Write Tokens](../how-to-guides/create-write-tokens.md).
- A working Go toolchain. The current OpenTelemetry Go modules require Go 1.25 or newer.

!!! note "This sends your data to Logfire"
    The steps below send your app's data to Logfire, where it is stored. To keep data on your own infrastructure while you evaluate, [send it to a local backend](../how-to-guides/alternative-backends.md) instead. Your write token is a secret, so keep it out of source control.

## Send your first trace

**1. Configure the exporter**

Point the OpenTelemetry Go SDK at Logfire with three environment variables: the endpoint, your write token, and a service name.

```sh
export OTEL_EXPORTER_OTLP_ENDPOINT=https://logfire-us.pydantic.dev
export OTEL_EXPORTER_OTLP_HEADERS='Authorization=your-write-token'
export OTEL_SERVICE_NAME=hello-go
```

The endpoint above is for the US [data region](../reference/data-regions.md). If your project is in the EU region, use `https://logfire-eu.pydantic.dev` instead. `OTEL_SERVICE_NAME` sets how your service appears in Logfire; without it, spans show under `unknown_service`.

**2. Add the code**

```go title="main.go"
package main

import (
    "context"
    "log"

    "go.opentelemetry.io/otel"
    "go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracehttp"
    sdktrace "go.opentelemetry.io/otel/sdk/trace"
)

func main() {
    ctx := context.Background()

    // otlptracehttp.New reads OTEL_EXPORTER_OTLP_ENDPOINT and
    // OTEL_EXPORTER_OTLP_HEADERS from the environment.
    exporter, err := otlptracehttp.New(ctx)
    if err != nil {
        log.Fatalf("failed to create exporter: %v", err)
    }

    tracerProvider := sdktrace.NewTracerProvider(sdktrace.WithBatcher(exporter))
    otel.SetTracerProvider(tracerProvider)
    defer func() {
        // Shutdown flushes any spans still in the batch before the program exits.
        if err := tracerProvider.Shutdown(ctx); err != nil {
            log.Fatalf("failed to shut down tracer provider: %v", err)
        }
    }()

    _, span := otel.Tracer("hello-go").Start(ctx, "hello")
    span.End()
}
```

This uses the OpenTelemetry Protocol (OTLP) HTTP exporter (`otlptracehttp`), which is the transport Logfire accepts, so you do not need to set `OTEL_EXPORTER_OTLP_PROTOCOL`.

**3. Run it**

```sh
go mod init hello-go
go mod tidy
go run .
```

## See it in the Live view

Open the [**Live view**](../guides/web-ui/live.md) in Logfire. Your `hello` span appears as it arrives:

![Traces arriving in the Logfire Live view](../images/logfire-live-view.png)

Each row is one span, with its service, name, and duration. The screenshot shows a busier app; your run appears as its own row, service `hello-go` and span `hello`, which you can click to open the full trace.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Nothing appears in the Live view | Missing or wrong write token | Confirm `OTEL_EXPORTER_OTLP_HEADERS` is `Authorization=<your token>` in the same shell that runs the program, and that the token belongs to the project you are viewing |
| The program exits with no data | It exited before the batch was flushed | Keep the `defer ...Shutdown(ctx)` so buffered spans are sent on exit |
| No error, but still no data | Export happens in the background, so failures are not returned inline | Log background failures with `otel.SetErrorHandler(...)`, and check the endpoint matches your [data region](../reference/data-regions.md) |

## Next steps

- **New to tracing?** [Core concepts](../concepts.md) explains spans and traces and how to read them.
- **Want automatic traces?** The [OpenTelemetry Go contrib packages](https://github.com/open-telemetry/opentelemetry-go-contrib) instrument `net/http`, gRPC, and database drivers; they use the global provider you set with `otel.SetTracerProvider`.
- **Another language?** See [Language support](../instrument/index.md), or [Alternative clients](../how-to-guides/alternative-clients.md) for the generic pattern.
