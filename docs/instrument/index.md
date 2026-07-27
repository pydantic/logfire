---
title: "Instrument your app"
description: "Get your application's telemetry into Logfire: choose your language and add a few lines, or attach an agent."
---

# Instrument your app

Instrumentation is how your app's work reaches Logfire. You add a few lines (or attach an agent) once, and every request, database query, and error shows up as a **trace** (the full journey of one request, made of nested **spans**, where a span is one unit of work with a name, a start, and a duration). From then on you read the traces instead of adding logging by hand.

Logfire is built on [OpenTelemetry (OTel)](https://opentelemetry.io/), the open industry standard for collecting traces, metrics, and logs, so it works with any language OpenTelemetry supports.

## Choose your language

Each guide takes you from install to your first trace in a few minutes:

- **[Python](../guides/onboarding-checklist/index.md)**: the Logfire Python SDK, with a framework picker and auto-tracing.
- **[TypeScript](https://pydantic.dev/docs/logfire/typescript-sdk/)**: the Logfire TypeScript SDK for Node.js, browsers, and edge runtimes.
- **[Rust](../languages/rust.md)**: the first-party `logfire` crate.
- **[Go](../languages/go.md)**: the standard OpenTelemetry Go SDK.
- **[.NET](../languages/dotnet.md)**: the standard OpenTelemetry .NET SDK.
- **[Java](../languages/java.md)**: the zero-code OpenTelemetry agent, no code changes.
- **[Ruby](../languages/ruby.md)**: the standard OpenTelemetry Ruby SDK.
- **[PHP](../languages/php.md)**: the standard OpenTelemetry PHP SDK.

Using something else? Any OpenTelemetry-compatible client can send to Logfire: see [Alternative clients](../how-to-guides/alternative-clients.md).

## Next steps

Once your app is sending data:

- **See it arrive** in the [Live view](../guides/web-ui/live.md).
- **Instrument the libraries you already use** (web framework, database driver, HTTP client) with [Integrations](../integrations/index.md).
- **New to tracing?** [Core concepts](../concepts.md) explains spans and traces and how to read them.
