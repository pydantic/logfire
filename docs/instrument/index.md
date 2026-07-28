---
title: "Instrument your app"
description: "Get your application's telemetry into Logfire: choose your language and add a few lines, or attach an agent."
---

# Instrument your app

Instrumentation is how your app's work reaches Logfire. You add a few lines (or attach an agent) once, and every request, database query, and error shows up as a **trace** (the full journey of one request, made of nested **spans**, where a span is one unit of work with a name, a start, and a duration). From then on you read the traces instead of adding logging by hand.

Logfire is built on [OpenTelemetry (OTel)](https://opentelemetry.io/), the open industry standard for collecting traces, metrics, and logs, so it works with any language OpenTelemetry supports.

## Native Logfire SDKs

These wrap OpenTelemetry in an idiomatic API for each language, with streamlined setup and extra features. Each guide takes you from install to your first trace in a few minutes:

<div class="integration-grid">
  <a class="integration-card" href="../guides/onboarding-checklist/index.md">
    <span class="integration-logo integration-logo--glyph" style="-webkit-mask: url(../images/languages/python.svg) center/contain no-repeat; mask: url(../images/languages/python.svg) center/contain no-repeat"></span>
    <span class="integration-name">Python</span>
  </a>
  <a class="integration-card" href="https://pydantic.dev/docs/logfire/typescript-sdk/">
    <span class="integration-logo integration-logo--glyph" style="-webkit-mask: url(../images/languages/typescript.svg) center/contain no-repeat; mask: url(../images/languages/typescript.svg) center/contain no-repeat"></span>
    <span class="integration-name">JavaScript / TypeScript</span>
  </a>
  <a class="integration-card" href="../languages/rust.md">
    <span class="integration-logo integration-logo--glyph" style="-webkit-mask: url(../images/languages/rust.svg) center/contain no-repeat; mask: url(../images/languages/rust.svg) center/contain no-repeat"></span>
    <span class="integration-name">Rust</span>
  </a>
</div>

## Any language via OpenTelemetry

For a language without a dedicated SDK, send data with the standard OpenTelemetry SDK. We have setup guides for:

<div class="integration-grid">
  <a class="integration-card" href="../languages/go.md">
    <span class="integration-logo integration-logo--glyph" style="-webkit-mask: url(../images/languages/go.svg) center/contain no-repeat; mask: url(../images/languages/go.svg) center/contain no-repeat"></span>
    <span class="integration-name">Go</span>
  </a>
  <a class="integration-card" href="../languages/dotnet.md">
    <span class="integration-logo integration-logo--glyph" style="-webkit-mask: url(../images/languages/dotnet.svg) center/contain no-repeat; mask: url(../images/languages/dotnet.svg) center/contain no-repeat"></span>
    <span class="integration-name">.NET</span>
  </a>
  <a class="integration-card" href="../languages/java.md">
    <span class="integration-logo integration-logo--glyph" style="-webkit-mask: url(../images/languages/java.svg) center/contain no-repeat; mask: url(../images/languages/java.svg) center/contain no-repeat"></span>
    <span class="integration-name">Java</span>
  </a>
  <a class="integration-card" href="../languages/ruby.md">
    <span class="integration-logo integration-logo--glyph" style="-webkit-mask: url(../images/languages/ruby.svg) center/contain no-repeat; mask: url(../images/languages/ruby.svg) center/contain no-repeat"></span>
    <span class="integration-name">Ruby</span>
  </a>
  <a class="integration-card" href="../languages/php.md">
    <span class="integration-logo integration-logo--glyph" style="-webkit-mask: url(../images/languages/php.svg) center/contain no-repeat; mask: url(../images/languages/php.svg) center/contain no-repeat"></span>
    <span class="integration-name">PHP</span>
  </a>
  <a class="integration-card" href="../how-to-guides/alternative-clients.md">
    <span class="integration-logo integration-logo--plainmark">+</span>
    <span class="integration-name">Any other language</span>
  </a>
</div>

## Next steps

Once your app is sending data:

- **See it arrive** in the [Live view](../guides/web-ui/live.md).
- **Instrument the libraries you already use** (web framework, database driver, HTTP client) with [Integrations](../integrations/index.md).
- **New to tracing?** [Core concepts](../concepts.md) explains spans and traces and how to read them.
