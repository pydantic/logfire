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
  <a class="integration-card" href="onboarding-checklist/">
    <span class="integration-logo integration-logo--glyph" style="--glyph: url(../images/languages/python.svg)"></span>
    <span class="integration-name">Python</span>
  </a>
  <a class="integration-card" href="../typescript-sdk/">
    <span class="integration-logo integration-logo--glyph" style="--glyph: url(../images/languages/typescript.svg)"></span>
    <span class="integration-name">JavaScript / TypeScript</span>
  </a>
  <a class="integration-card" href="rust/">
    <span class="integration-logo integration-logo--glyph" style="--glyph: url(../images/languages/rust.svg)"></span>
    <span class="integration-name">Rust</span>
  </a>
</div>

## Any language via OpenTelemetry

For a language without a dedicated SDK, send data with the standard OpenTelemetry SDK. We have setup guides for:

<div class="integration-grid">
  <a class="integration-card" href="go/">
    <span class="integration-logo integration-logo--glyph" style="--glyph: url(../images/languages/go.svg)"></span>
    <span class="integration-name">Go</span>
  </a>
  <a class="integration-card" href="dotnet/">
    <span class="integration-logo integration-logo--glyph" style="--glyph: url(../images/languages/dotnet.svg)"></span>
    <span class="integration-name">.NET</span>
  </a>
  <a class="integration-card" href="java/">
    <span class="integration-logo integration-logo--glyph" style="--glyph: url(../images/languages/java.svg)"></span>
    <span class="integration-name">Java</span>
  </a>
  <a class="integration-card" href="ruby/">
    <span class="integration-logo integration-logo--glyph" style="--glyph: url(../images/languages/ruby.svg)"></span>
    <span class="integration-name">Ruby</span>
  </a>
  <a class="integration-card" href="php/">
    <span class="integration-logo integration-logo--glyph" style="--glyph: url(../images/languages/php.svg)"></span>
    <span class="integration-name">PHP</span>
  </a>
  <a class="integration-card" href="../guides/alternative-clients/">
    <span class="integration-logo integration-logo--plainmark">+</span>
    <span class="integration-name">Any other language</span>
  </a>
</div>

## Next steps

Once your app is sending data:

- **See it arrive** in the [Live view](../guides/web-ui/live.md).
- **Instrument the libraries you already use** (web framework, database driver, HTTP client) with [Integrations](../integrations/index.md).
- **New to tracing?** [Core concepts](../concepts.md) explains spans and traces and how to read them.
