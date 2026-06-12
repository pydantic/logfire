---
title: "Pydantic Logfire Integrations: Semantic Kernel (.NET)"
description: "Send Microsoft Semantic Kernel (.NET) telemetry to Pydantic Logfire using the OpenTelemetry .NET SDK and an OTLP exporter."
integration: otel
---
# Semantic Kernel (.NET)

[Microsoft Semantic Kernel](https://learn.microsoft.com/en-us/semantic-kernel/) for .NET has native
OpenTelemetry support via `ActivitySource` and `Meter` (model diagnostics following the
[OTel GenAI semantic conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/)). You send that
telemetry to **Logfire** with the standard OpenTelemetry .NET SDK plus an OTLP exporter pointed at **Logfire**.

## Installation

```bash
dotnet add package Microsoft.SemanticKernel
dotnet add package OpenTelemetry.Exporter.OpenTelemetryProtocol
```

## Usage

Semantic Kernel emits GenAI spans only when you enable its experimental diagnostics. Enable them (the
`Sensitive` switch also records prompts and completions), register the `Microsoft.SemanticKernel*` sources and
meters, and export over OTLP to **Logfire**:

```csharp title="Program.cs"
using Microsoft.SemanticKernel;
using OpenTelemetry;
using OpenTelemetry.Metrics;
using OpenTelemetry.Resources;
using OpenTelemetry.Trace;

const string LogfireBase = "https://logfire-us.pydantic.dev"; // or logfire-eu.pydantic.dev
string logfireToken = Environment.GetEnvironmentVariable("LOGFIRE_TOKEN")!;
string authHeader = $"Authorization={logfireToken}";

// Enable GenAI diagnostics + prompt/response content. Set before building providers.
AppContext.SetSwitch("Microsoft.SemanticKernel.Experimental.GenAI.EnableOTelDiagnosticsSensitive", true);

var resource = ResourceBuilder.CreateDefault().AddService("sk-agent");

// NOTE: with HttpProtobuf + per-signal AddOtlpExporter you must supply the FULL /v1/* path.
using var tracerProvider = Sdk.CreateTracerProviderBuilder()
    .SetResourceBuilder(resource)
    .AddSource("Microsoft.SemanticKernel*")
    .AddOtlpExporter(o =>
    {
        o.Endpoint = new Uri($"{LogfireBase}/v1/traces");
        o.Protocol = OpenTelemetry.Exporter.OtlpExportProtocol.HttpProtobuf;
        o.Headers = authHeader;
    })
    .Build();

using var meterProvider = Sdk.CreateMeterProviderBuilder()
    .SetResourceBuilder(resource)
    .AddMeter("Microsoft.SemanticKernel*")
    .AddOtlpExporter(o =>
    {
        o.Endpoint = new Uri($"{LogfireBase}/v1/metrics");
        o.Protocol = OpenTelemetry.Exporter.OtlpExportProtocol.HttpProtobuf;
        o.Headers = authHeader;
    })
    .Build();

var kernel = Kernel.CreateBuilder()
    .AddOpenAIChatCompletion("gpt-4o", Environment.GetEnvironmentVariable("OPENAI_API_KEY")!)
    .Build();

var answer = await kernel.InvokePromptAsync("Why is the sky blue in one sentence?");
Console.WriteLine(answer);
// Providers flush on Dispose (end of `using` scope).
```

You'll see the LLM call span with model, token usage, and (because the sensitive switch is on) the prompt and
completion in **Logfire**.

!!! warning "Common pitfalls"
    - **Default OTLP protocol is gRPC.** **Logfire** ingests OTLP/HTTP, so you must set
      `OtlpExportProtocol.HttpProtobuf`, and with per-signal `AddOtlpExporter` supply the **full** path
      (`/v1/traces`, `/v1/metrics`) yourself — it isn't appended automatically.
    - **No diagnostics, no spans.** Without `EnableOTelDiagnostics` (metadata) or
      `EnableOTelDiagnosticsSensitive` (also prompts/completions), SK's AI connectors emit nothing. Set the
      switch (or env var `SEMANTICKERNEL_EXPERIMENTAL_GENAI_ENABLE_OTEL_DIAGNOSTICS[_SENSITIVE]=true`) before
      the first call. Enable `Sensitive` only in dev/test.
    - **Wildcard sources/meters.** Use `Microsoft.SemanticKernel*` — individual connector meters live under
      sub-namespaces.
    - **Providers must outlive your app and be disposed** (they flush on dispose). In a long-lived service,
      register them in DI as singletons.

!!! tip "Env-var alternative"
    Instead of per-signal endpoints in code, set `OTEL_EXPORTER_OTLP_ENDPOINT=https://logfire-us.pydantic.dev`
    (base URL), `OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf`, and
    `OTEL_EXPORTER_OTLP_HEADERS=Authorization=<token>`. A bare `.AddOtlpExporter()` then picks these up and
    appends the signal paths for you.

## Managed prompts

Managed prompts are authored and versioned in
[Prompt Management](../../reference/advanced/prompt-management/index.md). The dedicated prompt-fetching SDK
helpers currently ship in the [Python](../../reference/advanced/prompt-management/application.md) and
[TypeScript](https://pydantic.dev/docs/logfire/typescript-sdk/) SDKs. From .NET you can consume managed
variables over the language-agnostic [OFREP HTTP API](../../reference/advanced/managed-variables/external.md),
or resolve the prompt in a small Python/TypeScript sidecar and pass the rendered text into your kernel prompt.
