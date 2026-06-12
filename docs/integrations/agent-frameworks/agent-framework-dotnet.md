---
title: "Pydantic Logfire Integrations: Microsoft Agent Framework (.NET)"
description: "Send Microsoft Agent Framework (.NET, Microsoft.Agents.AI) telemetry to Pydantic Logfire using the OpenTelemetry .NET SDK and an OTLP exporter."
integration: otel
---
# Microsoft Agent Framework (.NET)

The [Microsoft Agent Framework](https://learn.microsoft.com/en-us/agent-framework/) (namespace
`Microsoft.Agents.AI`) is Microsoft's GA framework that unifies Semantic Kernel and AutoGen. It builds on
`Microsoft.Extensions.AI` and emits OpenTelemetry traces and metrics following the
[OTel GenAI semantic conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/), so you send its
telemetry to **Logfire** with the standard OpenTelemetry .NET SDK plus an OTLP exporter.

## Installation

```bash
dotnet add package Microsoft.Agents.AI
dotnet add package Microsoft.Agents.AI.OpenAI
dotnet add package OpenTelemetry.Exporter.OpenTelemetryProtocol
```

## Usage

Enable OpenTelemetry on the chat client and/or the agent with a shared `sourceName`, register that source, and
export over OTLP to **Logfire**:

```csharp title="Program.cs"
using System.ClientModel;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;
using OpenAI;
using OpenTelemetry;
using OpenTelemetry.Resources;
using OpenTelemetry.Trace;

const string LogfireBase = "https://logfire-us.pydantic.dev"; // or logfire-eu.pydantic.dev
const string SourceName = "weather-agent";                    // one name for client + agent
string logfireToken = Environment.GetEnvironmentVariable("LOGFIRE_TOKEN")!;

var resource = ResourceBuilder.CreateDefault().AddService("maf-agent");

// HttpProtobuf + per-signal exporter => supply the FULL /v1/traces path.
using var tracerProvider = Sdk.CreateTracerProviderBuilder()
    .SetResourceBuilder(resource)
    .AddSource(SourceName) // must match the UseOpenTelemetry/WithOpenTelemetry sourceName
    .AddOtlpExporter(o =>
    {
        o.Endpoint = new Uri($"{LogfireBase}/v1/traces");
        o.Protocol = OpenTelemetry.Exporter.OtlpExportProtocol.HttpProtobuf;
        o.Headers = $"Authorization={logfireToken}";
    })
    .Build();

// Build an instrumented IChatClient from the OpenAI client.
IChatClient chatClient = new OpenAIClient(
        new ApiKeyCredential(Environment.GetEnvironmentVariable("OPENAI_API_KEY")!))
    .GetChatClient("gpt-4o")
    .AsIChatClient()
    .AsBuilder()
    .UseOpenTelemetry(sourceName: SourceName, configure: cfg => cfg.EnableSensitiveData = true)
    .Build();

AIAgent agent = new ChatClientAgent(
        chatClient,
        name: "WeatherAgent",
        instructions: "You are a concise, helpful assistant.")
    .WithOpenTelemetry(sourceName: SourceName, configure: cfg => cfg.EnableSensitiveData = true);

var response = await agent.RunAsync("Why is the sky blue in one sentence?");
Console.WriteLine(response);
```

You'll see `invoke_agent`, `chat`, and (if the agent calls tools) `execute_tool` spans, plus
`gen_ai.client.*` metrics, in **Logfire**.

!!! warning "Common pitfalls"
    - **Default OTLP protocol is gRPC.** Set `OtlpExportProtocol.HttpProtobuf` and supply the full `/v1/traces`
      path with per-signal `AddOtlpExporter` (it isn't appended automatically).
    - **`sourceName` must match `AddSource`.** If you omit `sourceName`, register the defaults instead:
      `AddSource("Experimental.Microsoft.Agents.AI")` (agent) and
      `AddSource("Experimental.Microsoft.Extensions.AI")` (chat client).
    - **Don't double-instrument unnecessarily.** Enabling OTel on **both** the chat client and the agent (with
      `EnableSensitiveData`) duplicates prompt/response content across `chat` and `invoke_agent` spans.
      Instrument one layer if duplication is a problem.
    - **`EnableSensitiveData = true`** captures prompts, responses, and tool args — dev/test only.

!!! tip "Env-var alternative"
    Set `OTEL_EXPORTER_OTLP_ENDPOINT=https://logfire-us.pydantic.dev` (base URL),
    `OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf`, and `OTEL_EXPORTER_OTLP_HEADERS=Authorization=<token>`, then a
    bare `.AddOtlpExporter()` picks them up and appends the signal paths.

## Managed prompts

Managed prompts are authored and versioned in
[Prompt Management](../../reference/advanced/prompt-management/index.md). The dedicated prompt-fetching SDK
helpers currently ship in the [Python](../../reference/advanced/prompt-management/application.md) and
[TypeScript](https://pydantic.dev/docs/logfire/typescript-sdk/) SDKs. From .NET you can consume managed
variables over the language-agnostic [OFREP HTTP API](../../reference/advanced/managed-variables/external.md),
or resolve the prompt in a small Python/TypeScript sidecar and pass the rendered text into the agent's
`instructions`.
