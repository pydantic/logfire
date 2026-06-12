---
title: "Pydantic Logfire Integrations: Rig (Rust)"
description: "Send Rig (rig-core) agent telemetry to Pydantic Logfire using the native Logfire Rust SDK or a standard OpenTelemetry OTLP exporter."
integration: otel
---
# Rig (Rust)

[Rig](https://docs.rig.rs/) (the `rig-core` crate) is a Rust framework for building LLM and agent applications.
It is instrumented with the [`tracing`](https://docs.rs/tracing) crate and emits **GenAI semantic-convention**
spans for completions, agents, and tools. Because Rig uses `tracing`, you export its spans to **Logfire** by
installing a subscriber that ships them over OpenTelemetry — the simplest being the native
[Logfire Rust SDK](https://github.com/pydantic/logfire-rust).

!!! note
    Rig emits spans, but nothing is exported until you install a subscriber. Set one up **before** building and
    prompting your agent.

## Option A — Logfire Rust SDK (recommended)

The `logfire` crate sets up the whole `tracing` + OpenTelemetry + OTLP-to-Logfire pipeline for you, so Rig's
spans flow through automatically.

```toml title="Cargo.toml"
[dependencies]
rig-core = "0.38"
logfire = "0.10"
tokio = { version = "1", features = ["macros", "rt-multi-thread"] }
tracing = "0.1"
```

```rust title="src/main.rs"
use logfire::config::SendToLogfire;
use rig::{completion::Prompt, providers::openai};

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    // Installs the global tracing subscriber + OTLP exporter to Logfire.
    // Reads LOGFIRE_TOKEN from the environment.
    let logfire = logfire::configure()
        .send_to_logfire(SendToLogfire::IfTokenPresent)
        .finish()?;
    let _guard = logfire.shutdown_guard(); // flushes spans on drop

    // Rig agent — spans emitted via `tracing` are captured automatically.
    let client = openai::Client::from_env();
    let agent = client
        .agent(openai::GPT_4O)
        .preamble("You are a helpful assistant.")
        .build();

    let answer = agent.prompt("In one sentence, what is observability?").await?;
    println!("{answer}");

    Ok(()) // `_guard` drops here, flushing to Logfire
}
```

Run with `LOGFIRE_TOKEN=<write-token> OPENAI_API_KEY=<key> cargo run`. You'll see the agent's completion span
with GenAI attributes (model, token usage) in **Logfire**.

For an EU-region project, set `OTEL_EXPORTER_OTLP_ENDPOINT=https://logfire-eu.pydantic.dev`.

## Option B — Standard OpenTelemetry OTLP exporter

If you'd rather not use the Logfire crate, wire `tracing-subscriber` → `tracing-opentelemetry` →
`opentelemetry-otlp` and point the exporter at **Logfire**'s OTLP/HTTP endpoint.

```toml title="Cargo.toml"
[dependencies]
rig-core = "0.38"
tokio = { version = "1", features = ["macros", "rt-multi-thread"] }
opentelemetry = "0.31"
opentelemetry_sdk = { version = "0.31", features = ["rt-tokio"] }
opentelemetry-otlp = { version = "0.31", features = ["http-proto", "reqwest-client"] }
tracing = "0.1"
tracing-subscriber = { version = "0.3", features = ["env-filter"] }
tracing-opentelemetry = "0.32" # 0.32 pairs with opentelemetry 0.31
```

```rust title="src/main.rs"
use opentelemetry::trace::TracerProvider as _;
use opentelemetry::KeyValue;
use opentelemetry_sdk::{trace::SdkTracerProvider, Resource};
use rig::{completion::Prompt, providers::openai};
use tracing_subscriber::prelude::*;

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    // Reads OTEL_EXPORTER_OTLP_ENDPOINT and
    // OTEL_EXPORTER_OTLP_HEADERS (Authorization=<write-token>) from env.
    let exporter = opentelemetry_otlp::SpanExporter::builder().with_http().build()?;
    let provider = SdkTracerProvider::builder()
        .with_batch_exporter(exporter)
        .with_resource(Resource::builder().with_attributes([KeyValue::new("service.name", "rig-demo")]).build())
        .build();

    let tracer = provider.tracer("rig-demo");
    tracing_subscriber::registry()
        .with(tracing_opentelemetry::layer().with_tracer(tracer))
        .init();

    let client = openai::Client::from_env();
    let agent = client.agent(openai::GPT_4O).preamble("You are a helpful assistant.").build();
    let answer = agent.prompt("In one sentence, what is observability?").await?;
    println!("{answer}");

    provider.shutdown()?; // MUST flush the batch exporter before exit, or spans are lost
    Ok(())
}
```

```bash
export OTEL_EXPORTER_OTLP_ENDPOINT="https://logfire-us.pydantic.dev"
export OTEL_EXPORTER_OTLP_HEADERS="Authorization=your-write-token"
```

!!! warning "Common pitfalls"
    - **Install a subscriber.** Rig's spans are dropped unless a subscriber is registered, before the agent
      runs.
    - **Flush on shutdown** — the most common cause of "no data". Keep the `ShutdownGuard` alive (Option A) or
      call `provider.shutdown()` (Option B) before the process exits.
    - **Version compatibility is the sharpest edge.** All `opentelemetry*` crates must share the same minor
      (all `0.31`), and `tracing-opentelemetry` is one minor ahead (`0.32` ↔ `opentelemetry 0.31`). The
      `logfire` crate already pins a consistent set. Verify current versions on crates.io before pinning.
    - **Use OTLP HTTP/protobuf** (feature `http-proto`); the SDK appends `/v1/traces` to the base endpoint.

## Managed prompts

Managed prompts are authored and versioned in
[Prompt Management](../../reference/advanced/prompt-management/index.md). The dedicated prompt-fetching SDK
helpers are currently available in the [Python](../../reference/advanced/prompt-management/application.md) and
[TypeScript](https://pydantic.dev/docs/logfire/typescript-sdk/) SDKs. From Rust, you can still consume managed
variables over the language-agnostic
[OFREP HTTP API](../../reference/advanced/managed-variables/external.md), or resolve the prompt in a small
Python/TypeScript sidecar and pass the rendered text into your Rig `preamble`/prompt.
