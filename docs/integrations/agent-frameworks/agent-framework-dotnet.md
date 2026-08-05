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

Enable OpenTelemetry on the agent, register the same `sourceName` with the OpenTelemetry provider, and export
over OTLP to **Logfire**. For a `ChatClientAgent`, the agent integration also instruments its underlying chat
client, so you do not need to wrap the chat client separately:

```csharp title="Program.cs"
using System.ClientModel;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;
using OpenAI;
using OpenTelemetry;
using OpenTelemetry.Resources;
using OpenTelemetry.Trace;

const string LogfireBase = "https://logfire-us.pydantic.dev"; // or logfire-eu.pydantic.dev
const string SourceName = "incident-agent";                   // one name for client + agent
string logfireToken = Environment.GetEnvironmentVariable("LOGFIRE_TOKEN")!;

var resource = ResourceBuilder.CreateDefault().AddService("maf-agent");

// HttpProtobuf + per-signal exporter => supply the FULL /v1/traces path.
using var tracerProvider = Sdk.CreateTracerProviderBuilder()
    .SetResourceBuilder(resource)
    .AddSource(SourceName) // must match the UseOpenTelemetry sourceName
    .AddOtlpExporter(o =>
    {
        o.Endpoint = new Uri($"{LogfireBase}/v1/traces");
        o.Protocol = OpenTelemetry.Exporter.OtlpExportProtocol.HttpProtobuf;
        o.Headers = $"Authorization={logfireToken}";
    })
    .Build();

// Build the IChatClient used by the real agent. The agent's OpenTelemetry
// integration below automatically instruments this client too.
IChatClient chatClient = new OpenAIClient(
        new ApiKeyCredential(Environment.GetEnvironmentVariable("OPENAI_API_KEY")!))
    .GetChatClient("gpt-4o")
    .AsIChatClient();

int toolCalls = 0;
AIAgent agent = new ChatClientAgent(
        chatClient,
        name: "IncidentAgent",
        instructions: "Use lookup_incident to verify the incident before answering.",
        tools:
        [
            AIFunctionFactory.Create(
                (string incidentId) =>
                {
                    toolCalls++;
                    return $"{incidentId} is resolved; owner=platform-observability";
                },
                name: "lookup_incident",
                description: "Look up the current status and owner of an incident by ID.")
        ])
    .AsBuilder()
    .UseOpenTelemetry(sourceName: SourceName, configure: cfg => cfg.EnableSensitiveData = true)
    .Build();

var response = await agent.RunAsync(
    "Use lookup_incident with incidentId incident-42, then report the status and owner.");
if (toolCalls == 0)
{
    throw new InvalidOperationException("Expected the agent to call lookup_incident.");
}
Console.WriteLine(response);
```

This uses Microsoft Agent Framework's real `ChatClientAgent` and `AIFunction`; no wrapper spans are added.
You'll see `invoke_agent`, `chat`, and `execute_tool` spans in **Logfire**. To also
collect `gen_ai.client.*` metrics, configure a `MeterProvider` with `AddMeter(SourceName)` and an OpenTelemetry
Protocol metrics exporter.

!!! warning "Common pitfalls"
    - **Default OTLP protocol is gRPC.** Set `OtlpExportProtocol.HttpProtobuf` and supply the full `/v1/traces`
      path with per-signal `AddOtlpExporter` (it isn't appended automatically).
    - **`sourceName` must match `AddSource`.** If you omit `sourceName`, register the defaults instead:
      `AddSource("Experimental.Microsoft.Agents.AI")` (agent) and
      `AddSource("Experimental.Microsoft.Extensions.AI")` (chat client).
    - **Let the agent instrument its chat client.** Current `OpenTelemetryAgent` automatically adds the inner
      `chat` and `execute_tool` spans for a `ChatClientAgent`. The inner client uses the same `sourceName`, and
      changes to `EnableSensitiveData` are propagated to it. Wrapping the chat client yourself is unnecessary.
    - **`EnableSensitiveData = true`** captures prompts, responses, function arguments, and function results on
      the native `invoke_agent` and `chat` spans. This data may include personally identifiable information
      (PII); enable it only for workloads whose telemetry destination and retention policy you trust.

!!! tip "Env-var alternative"
    Set `OTEL_EXPORTER_OTLP_ENDPOINT=https://logfire-us.pydantic.dev` (base URL),
    `OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf`, and `OTEL_EXPORTER_OTLP_HEADERS=Authorization=<token>`, then a
    bare `.AddOtlpExporter()` picks them up and appends the signal paths.

## Managed prompts

Managed prompts are authored and versioned in
[Prompt Management](../../reference/advanced/prompt-management/index.md). The dedicated prompt-fetching SDK
helpers currently ship in the [Python](../../reference/advanced/prompt-management/application.md) and
[TypeScript](https://pydantic.dev/docs/logfire/typescript-sdk/) SDKs. From .NET you can consume managed
variables over the language-agnostic
[OpenFeature Remote Evaluation Protocol (OFREP) HTTP API](../../reference/advanced/managed-variables/external.md),
or resolve the prompt in a small Python/TypeScript sidecar and pass the rendered text into the agent's
`instructions`.
