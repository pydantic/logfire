---
title: "Send traces from Rust"
description: "Send traces and logs from a Rust application to Logfire with the official logfire crate."
---

# Rust

See what your Rust application is doing in Logfire: the work it performed, how long each step took, and which steps failed. This takes about five minutes.

Rust has a dedicated Logfire SDK, the [`logfire`](https://crates.io/crates/logfire) crate. It builds on [OpenTelemetry (OTel)](https://opentelemetry.io/), the open industry standard for collecting traces, metrics, and logs, and on the popular [`tracing`](https://docs.rs/tracing) library, so it fits code you have already instrumented. You get **traces** (the full journey of one request, made of nested **spans**, where a span is one unit of work with a name, a start, and a duration) in the Logfire UI with a few lines of setup.

## Before you start

You need:

- A Logfire project and a **write token** (the credential your app uses to send data to a Logfire project). Copy one from **Project → Settings → Write tokens**; see [Create Write Tokens](../how-to-guides/create-write-tokens.md).
- A working Rust toolchain (`cargo`).

The token encodes which [data region](../reference/data-regions.md) your project is in (US or EU), so the SDK sends to the correct place automatically. You do not set an endpoint. Running a self-hosted Logfire? Set `LOGFIRE_BASE_URL` to your instance's URL.

!!! note "This sends your data to Logfire"
    The steps below send your app's data to Logfire, where it is stored. To keep data on your own infrastructure while you evaluate, [send it to a local backend](../how-to-guides/alternative-backends.md) instead. Your write token is a secret, so keep it out of source control.

## Send your first trace

**1. Create a project and add the crate**

```sh
cargo new hello-rust
cd hello-rust
cargo add logfire
```

`cargo add` adds a line like `logfire = "0.11"` to your `Cargo.toml`. Already have a project? Run `cargo add logfire` in it.

**2. Add the code**

```rust title="src/main.rs"
fn main() -> Result<(), Box<dyn std::error::Error>> {
    // Reads LOGFIRE_TOKEN from the environment. The region is taken from the token.
    let logfire = logfire::configure()
        .send_to_logfire(logfire::config::SendToLogfire::IfTokenPresent)
        .with_service_name("hello-rust")
        .finish()?;

    // The guard flushes and shuts Logfire down when it goes out of scope (end of main).
    let _guard = logfire.shutdown_guard();

    // A span records one operation; the log inside it is nested in that span.
    logfire::span!("hello").in_scope(|| {
        logfire::info!("Hello world");
    });

    Ok(())
}
```

**3. Run it**

```sh
export LOGFIRE_TOKEN=your-write-token
cargo run
```

## See it in the Live view

Open the [**Live view**](../guides/web-ui/live.md) in Logfire. Your `hello` trace appears as it arrives:

![Traces arriving in the Logfire Live view](../images/logfire-live-view.png)

Each row is one span, with its service, name, and duration. The screenshot shows a busier app; your run appears as its own row, service `hello-rust` and span `hello`. Click it to open the full trace: the `Hello world` log is nested inside.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Nothing appears in Logfire, and there's no error | `LOGFIRE_TOKEN` is not set: with `IfTokenPresent`, a missing token disables sending silently | Set the `LOGFIRE_TOKEN` environment variable |
| The token is set but nothing appears | Records are buffered and sent on shutdown | Keep the `let _guard = logfire.shutdown_guard();` binding alive for the whole run, or call `.shutdown()` explicitly |
| Can't tell what is happening | No local visibility | Add `.with_console(Some(logfire::config::ConsoleOptions::default()))` when configuring to print records to your terminal, or set `RUST_LOG` to see the SDK's own logs |

## Next steps

- **New to tracing?** [Core concepts](../concepts.md) explains spans and traces and how to read them.
- **Want the full API?** Read [docs.rs/logfire](https://docs.rs/logfire) and the source at [github.com/pydantic/logfire-rust](https://github.com/pydantic/logfire-rust); record your own work with the `logfire::span!` and `logfire::info!` macros.
- **Prefer raw OpenTelemetry?** See [Alternative clients](../how-to-guides/alternative-clients.md) for the standard OpenTelemetry SDK instead of the `logfire` crate.
