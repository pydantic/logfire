---
title: "Pydantic Logfire Integrations: Rig (Rust)"
description: "Send Rig agent, model, and tool telemetry to Pydantic Logfire using the Logfire Rust SDK."
integration: otel
---
# Rig (Rust)

[Rig](https://docs.rig.rs/) is a Rust framework for building large language model (LLM) and agent applications.
Rig emits [`tracing`](https://docs.rs/tracing) spans for agent, completion, and tool operations. The
[Logfire Rust SDK](https://github.com/pydantic/logfire-rust) installs the subscriber and OpenTelemetry exporter
that send those native spans to **Logfire**.

## Installation

```toml title="Cargo.toml"
[dependencies]
logfire = "0.11"
rig-agent = "0.41"
rig-core = "0.41"
serde = { version = "1", features = ["derive"] }
serde_json = "1"
tokio = { version = "1", features = ["macros", "rt-multi-thread"] }
```

## Usage

Configure Logfire before building the agent, then give the agent a real Rig `Tool`:

```rust title="src/main.rs"
use logfire::config::SendToLogfire;
use rig_agent::{
    client::AgentClientExt,
    completion::Prompt,
    tool::{Tool, ToolContext},
};
use rig_core::providers::openai;
use serde::Deserialize;
use std::{
    convert::Infallible,
    sync::{Arc, Mutex},
};

#[derive(Deserialize)]
struct IncidentInput {
    incident_id: String,
}

#[derive(Clone)]
struct LookupIncident(Arc<Mutex<Vec<String>>>);

impl Tool for LookupIncident {
    const NAME: &'static str = "lookup_incident";
    type Args = IncidentInput;
    type Output = String;
    type Error = Infallible;

    fn description(&self) -> String {
        "Look up the current status and owner of an incident by ID.".into()
    }

    fn parameters(&self) -> serde_json::Value {
        serde_json::json!({
            "type": "object",
            "properties": { "incident_id": { "type": "string" } },
            "required": ["incident_id"]
        })
    }

    async fn call(
        &self,
        _context: &mut ToolContext,
        args: Self::Args,
    ) -> Result<Self::Output, Self::Error> {
        self.0.lock().unwrap().push(args.incident_id.clone());
        Ok(format!(
            "{} is resolved; owner=platform-observability",
            args.incident_id
        ))
    }
}

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    // Requires LOGFIRE_TOKEN and installs the global tracing subscriber and exporter.
    let logfire = logfire::configure()
        .send_to_logfire(SendToLogfire::Yes)
        .finish()?;
    let guard = logfire.shutdown_guard();

    let client = openai::CompletionsClient::builder()
        .api_key(std::env::var("OPENAI_API_KEY")?)
        .build()?;
    let tool_calls = Arc::new(Mutex::new(Vec::new()));
    let agent = client
        .agent("gpt-4o-mini")
        .name("Incident agent")
        .preamble("Use the supplied tool to verify incidents before answering.")
        .default_max_turns(3)
        .tool(LookupIncident(tool_calls.clone()))
        .build();

    let answer = agent
        .prompt(
            "Call lookup_incident exactly once with incident_id incident-42, then report the status and owner.",
        )
        .await?;
    if tool_calls.lock().unwrap().as_slice() != ["incident-42"] {
        return Err("the agent did not execute lookup_incident exactly once".into());
    }
    println!("{answer}");

    guard.shutdown()?; // flushes spans before exit
    Ok(())
}
```

Run `LOGFIRE_TOKEN=<write-token> OPENAI_API_KEY=<key> cargo run` in your terminal. The program fails unless the
native Rig agent executes `lookup_incident`. In Logfire, the trace contains Rig's agent, completion, and tool
spans; the Logfire SDK does not add a synthetic agent wrapper.

For an EU-region project, use its EU write token. The Logfire Rust SDK infers the data region from the token.

!!! warning "Common pitfalls"
    - **Configure before constructing the agent.** Rig uses `tracing`; spans emitted before a subscriber is
      installed are lost.
    - **Flush before exit.** Keep the shutdown guard alive and call `guard.shutdown()` in short-lived programs.
    - **Use compatible crate generations.** The example was compiled with `rig-agent`/`rig-core` 0.41 and
      `logfire` 0.11. Rig split its agent APIs into `rig-agent`; examples written only against older `rig-core`
      releases do not use the current API.
    - For a hand-configured OpenTelemetry pipeline, all `opentelemetry*` crates must use compatible versions.
      The Logfire SDK already selects and configures a compatible set.

## Managed prompts

Managed prompts are authored and versioned in
[Prompt Management](../../reference/advanced/prompt-management/index.md). The dedicated prompt-fetching SDK
helpers are currently available in the [Python](../../reference/advanced/prompt-management/application.md) and
[TypeScript](https://pydantic.dev/docs/logfire/typescript-sdk/) SDKs. From Rust, consume managed variables over
the language-agnostic
[OpenFeature Remote Evaluation Protocol (OFREP) HTTP API](../../reference/advanced/managed-variables/external.md),
or resolve the prompt in a small Python or TypeScript sidecar and pass the rendered text into the Rig agent.
