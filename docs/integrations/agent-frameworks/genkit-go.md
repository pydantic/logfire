---
title: "Pydantic Logfire Integrations: Genkit (Go)"
description: "Send Firebase Genkit (Go) agent telemetry to Pydantic Logfire by registering a standard OpenTelemetry OTLP exporter as the global tracer provider."
integration: otel
---
# Genkit (Go)

[Firebase Genkit](https://genkit.dev/go/) for Go is built directly on the OpenTelemetry Go SDK and emits its
spans through the **global** `TracerProvider`. So to send Genkit traces to **Logfire**, register a standard
OpenTelemetry OTLP exporter (pointed at **Logfire**) as the global provider **before** `genkit.Init(...)` — and
Genkit's agent, model, and tool spans flow in automatically.

!!! note
    Don't use Genkit's `googlecloud.EnableGoogleCloudTelemetry` for **Logfire** — it targets Google Cloud
    Operations and has no generic OTLP endpoint. The standard OTel exporter below has no extra dependency on
    Genkit internals.

## Installation

```bash
go get github.com/firebase/genkit/go
go get go.opentelemetry.io/otel \
       go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracehttp \
       go.opentelemetry.io/otel/sdk
```

## Usage

```go title="main.go"
package main

import (
	"context"
	"fmt"

	"github.com/firebase/genkit/go/ai"
	"github.com/firebase/genkit/go/genkit"
	"github.com/firebase/genkit/go/plugins/googlegenai"
	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracehttp"
	"go.opentelemetry.io/otel/sdk/trace"
)

func main() {
	ctx := context.Background()

	// 1. Point the global OTel TracerProvider at Logfire (HTTP/protobuf).
	//    Endpoint + Authorization can also come from
	//    OTEL_EXPORTER_OTLP_ENDPOINT / OTEL_EXPORTER_OTLP_HEADERS.
	exp, _ := otlptracehttp.New(ctx,
		otlptracehttp.WithEndpointURL("https://logfire-us.pydantic.dev/v1/traces"),
		otlptracehttp.WithHeaders(map[string]string{"Authorization": "your-write-token"}),
	)
	tp := trace.NewTracerProvider(trace.WithBatcher(exp))
	defer tp.Shutdown(ctx)
	otel.SetTracerProvider(tp) // MUST be before genkit.Init

	// 2. Init Genkit; its spans now export to Logfire.
	g := genkit.Init(ctx,
		genkit.WithPlugins(&googlegenai.GoogleAI{}),
		genkit.WithDefaultModel("googleai/gemini-2.5-flash"),
	)

	resp, _ := genkit.Generate(ctx, g, ai.WithPrompt("Tell me a one-line joke about Go."))
	fmt.Println(resp.Text())
}
```

Set `GEMINI_API_KEY` (or your provider's key) and run `go run .`. You'll see the generation span with model and
token attributes in **Logfire**. Use `https://logfire-eu.pydantic.dev/v1/traces` for the EU region.

!!! warning "Common pitfalls"
    - **Set the global provider before `genkit.Init`**, or early spans are dropped.
    - **Use the HTTP exporter** (`otlptracehttp`) with the `/v1/traces` path — the gRPC exporter won't match
      Logfire's HTTP ingest.
    - **Flush on exit.** The `defer tp.Shutdown(ctx)` flushes the batch exporter; without it a short program may
      exit before spans are sent.

## Managed prompts

Managed prompts are authored and versioned in
[Prompt Management](../../reference/advanced/prompt-management/index.md). The dedicated prompt-fetching SDK
helpers currently ship in the [Python](../../reference/advanced/prompt-management/application.md) and
[TypeScript](https://pydantic.dev/docs/logfire/typescript-sdk/) SDKs. From Go you can consume managed variables
over the language-agnostic [OFREP HTTP API](../../reference/advanced/managed-variables/external.md), or resolve
the prompt in a small Python/TypeScript sidecar and pass the rendered text into `ai.WithPrompt(...)`.
