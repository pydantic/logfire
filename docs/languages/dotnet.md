---
title: "Send traces from .NET"
description: "Send traces from a .NET (C#) application to Logfire using the standard OpenTelemetry SDK."
---

# .NET

See what your .NET application is doing in Logfire: the requests it handles, how long each one took, and which ones failed. This takes about five minutes.

.NET does not have a dedicated Logfire SDK, but Logfire is built on [OpenTelemetry (OTel)](https://opentelemetry.io/), the open industry standard for collecting traces, metrics, and logs. The standard OpenTelemetry .NET SDK sends data straight to Logfire once you point it at the right endpoint, and you get **traces** (the full journey of one request, made of nested **spans**, where a span is one unit of work with a name, a start, and a duration) in the Logfire UI.

## Before you start

You need:

- A Logfire project and a **write token** (the credential your app uses to send data to a Logfire project). Copy one from **Project → Settings → Write tokens**; see [Create Write Tokens](../how-to-guides/create-write-tokens.md).
- A working .NET SDK.

!!! note "This sends your data to Logfire"
    The steps below send your app's data to Logfire, where it is stored. To keep data on your own infrastructure while you evaluate, [send it to a local backend](../how-to-guides/alternative-backends.md) instead. Your write token is a secret, so keep it out of source control.

## Send your first trace

**1. Create a project and add the exporter**

```sh
dotnet new console -o hello-dotnet
cd hello-dotnet
dotnet add package OpenTelemetry.Exporter.OpenTelemetryProtocol
```

This adds the OpenTelemetry Protocol (OTLP) exporter, the way you send data to Logfire.

**2. Configure the exporter**

```sh
export OTEL_EXPORTER_OTLP_ENDPOINT=https://logfire-us.pydantic.dev
export OTEL_EXPORTER_OTLP_HEADERS='Authorization=your-write-token'
export OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf
```

The endpoint above is for the US [data region](../reference/data-regions.md). If your project is in the EU region, use `https://logfire-eu.pydantic.dev` instead.

!!! warning "Set the protocol to `http/protobuf`"
    The .NET OTLP exporter defaults to gRPC, but Logfire receives data over OTLP on HTTP. You must set `OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf` (or set it in code, shown below), otherwise nothing is sent and you get a connection error.

**3. Add the code**

Replace the contents of `Program.cs`:

```csharp title="Program.cs"
using System.Diagnostics;
using OpenTelemetry;
using OpenTelemetry.Resources;
using OpenTelemetry.Trace;

// ActivitySource is .NET's built-in tracer.
var activitySource = new ActivitySource("hello-dotnet");

using var tracerProvider = Sdk.CreateTracerProviderBuilder()
    .AddSource("hello-dotnet")
    .ConfigureResource(r => r.AddService("hello-dotnet"))
    .AddOtlpExporter() // reads the OTEL_EXPORTER_OTLP_* environment variables, including the protocol
    .Build();

using (var activity = activitySource.StartActivity("hello"))
{
    activity?.SetTag("example", "true");
}

// Disposing the provider (end of the program) flushes and sends the span.
```

**4. Run it**

```sh
dotnet run
```

## See it in the Live view

Open the [**Live view**](../guides/web-ui/live.md) in Logfire. Your `hello` span appears as it arrives:

![Traces arriving in the Logfire Live view](../images/logfire-live-view.png)

Each row is one span, with its service, name, and duration. The screenshot shows a busier app; your run appears as its own row, service `hello-dotnet` and span `hello`, which you can click to open the full trace.

## Configure in code instead of environment variables

If you would rather not set environment variables, pass the options to `AddOtlpExporter`. When you set the endpoint in code you must include the signal path `/v1/traces` yourself:

```csharp
.AddOtlpExporter(o =>
{
    o.Endpoint = new Uri("https://logfire-us.pydantic.dev/v1/traces");
    o.Protocol = OtlpExportProtocol.HttpProtobuf;
    o.Headers = "Authorization=your-write-token";
})
```

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Connection refused, or nothing arrives | The exporter is still using its default gRPC protocol against Logfire's HTTP endpoint | Set `OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf`, or `Protocol = OtlpExportProtocol.HttpProtobuf` in code |
| Nothing exported even though config looks right | The tracer provider only records sources you register | Make sure `.AddSource("...")` matches the name you passed to `new ActivitySource("...")` |
| A 404 when configuring the endpoint in code | With `http/protobuf`, the code `Endpoint` property is used as-is and does not append the signal path | Include `/v1/traces` in the URL, or use the `OTEL_EXPORTER_OTLP_ENDPOINT` environment variable (which appends it for you) |
| Can't tell what the SDK is doing | No local visibility into what is being recorded | Add the `OpenTelemetry.Exporter.Console` package, then `.AddConsoleExporter()` to the builder, to print each span to your terminal as it is created |

## Next steps

- **New to tracing?** [Core concepts](../concepts.md) explains spans and traces and how to read them.
- **Building an ASP.NET Core app?** Add the `OpenTelemetry.Extensions.Hosting` package and automatic instrumentation for incoming requests, HTTP clients, and databases. See the [OpenTelemetry .NET docs](https://opentelemetry.io/docs/languages/dotnet/).
- **Another language?** See [Language support](../languages.md), or [Alternative clients](../how-to-guides/alternative-clients.md) for the generic pattern.
