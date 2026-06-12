---
title: "Pydantic Logfire Integrations: Eino (Go)"
description: "Send CloudWeGo Eino (Go) agent telemetry to Pydantic Logfire with a small OpenTelemetry callback handler over OTLP."
integration: otel
---
# Eino (Go)

[Eino](https://www.cloudwego.io/docs/eino/) is ByteDance/CloudWeGo's Go framework for LLM and agent
applications. Its observability is built on a **callbacks** system rather than automatic OpenTelemetry. To send
Eino traces to **Logfire**, register a standard OpenTelemetry OTLP exporter (pointed at **Logfire**) and a
small custom `callbacks.Handler` that opens a span per node on that provider.

!!! note
    The official `eino-ext` callback handlers (`apmplus`, `cozeloop`, `langfuse`) are vendor-specific and don't
    expose a generic OTLP endpoint with auth headers, so a tiny custom handler is the cleanest path to Logfire.

## Installation

```bash
go get github.com/cloudwego/eino
go get github.com/cloudwego/eino-ext/components/model/openai
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

	"github.com/cloudwego/eino-ext/components/model/openai"
	"github.com/cloudwego/eino/callbacks"
	"github.com/cloudwego/eino/components/model"
	"github.com/cloudwego/eino/schema"
	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracehttp"
	"go.opentelemetry.io/otel/sdk/trace"
	oteltrace "go.opentelemetry.io/otel/trace"
)

// Minimal handler that wraps each Eino node in an OTel span.
type otelHandler struct{ tr oteltrace.Tracer }

func (h *otelHandler) OnStart(ctx context.Context, info *callbacks.RunInfo, in callbacks.CallbackInput) context.Context {
	ctx, _ = h.tr.Start(ctx, info.Name)
	return ctx
}
func (h *otelHandler) OnEnd(ctx context.Context, info *callbacks.RunInfo, out callbacks.CallbackOutput) context.Context {
	if s := oteltrace.SpanFromContext(ctx); s != nil {
		s.End()
	}
	return ctx
}
func (h *otelHandler) OnError(ctx context.Context, info *callbacks.RunInfo, err error) context.Context {
	if s := oteltrace.SpanFromContext(ctx); s != nil {
		s.RecordError(err)
		s.End()
	}
	return ctx
}
func (h *otelHandler) OnStartWithStreamInput(ctx context.Context, _ *callbacks.RunInfo, in *schema.StreamReader[callbacks.CallbackInput]) context.Context {
	in.Close()
	return ctx
}
func (h *otelHandler) OnEndWithStreamOutput(ctx context.Context, _ *callbacks.RunInfo, out *schema.StreamReader[callbacks.CallbackOutput]) context.Context {
	out.Close()
	return ctx
}

func main() {
	ctx := context.Background()

	// 1. OTel -> Logfire (HTTP/protobuf).
	exp, _ := otlptracehttp.New(ctx,
		otlptracehttp.WithEndpointURL("https://logfire-us.pydantic.dev/v1/traces"),
		otlptracehttp.WithHeaders(map[string]string{"Authorization": "your-write-token"}),
	)
	tp := trace.NewTracerProvider(trace.WithBatcher(exp))
	defer tp.Shutdown(ctx)
	otel.SetTracerProvider(tp)

	// 2. Register the handler globally (init only — not thread-safe).
	callbacks.AppendGlobalHandlers(&otelHandler{tr: tp.Tracer("eino")})

	// 3. One model call -> traced to Logfire.
	cm, _ := openai.NewChatModel(ctx, &openai.ChatModelConfig{APIKey: "sk-...", Model: "gpt-4o-mini"})
	out, _ := cm.Generate(ctx,
		[]*schema.Message{schema.UserMessage("One-line joke about Go?")},
		model.WithTemperature(0.7),
	)
	fmt.Println(out.Content)
}
```

Use `https://logfire-eu.pydantic.dev/v1/traces` for the EU region.

!!! warning "Common pitfalls"
    - **`callbacks.AppendGlobalHandlers` is not thread-safe** — call it only at process init.
    - **Close the stream readers** in the streaming callback variants or you'll leak.
    - **Use the HTTP exporter** with the `/v1/traces` path, and **flush on exit** via `defer tp.Shutdown(ctx)`.
    - Component constructors (the OpenAI chat model here) live in the separate `eino-ext` module, not core
      `eino`.

## Managed prompts

Managed prompts are authored and versioned in
[Prompt Management](../../reference/advanced/prompt-management/index.md). The dedicated prompt-fetching SDK
helpers currently ship in the [Python](../../reference/advanced/prompt-management/application.md) and
[TypeScript](https://pydantic.dev/docs/logfire/typescript-sdk/) SDKs. From Go you can consume managed variables
over the language-agnostic [OFREP HTTP API](../../reference/advanced/managed-variables/external.md), or resolve
the prompt in a small Python/TypeScript sidecar and pass the rendered text into your Eino messages.
