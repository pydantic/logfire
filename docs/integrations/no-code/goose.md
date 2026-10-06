---
title: "Send Goose traces to Logfire"
description: "Configure Goose desktop or its command-line interface to send agent-session and tool traces to Pydantic Logfire."
integration: otel
---

# Send Goose traces to Logfire

See each Goose agent session as a trace (the full journey of one agent run, made of one or more spans) in Logfire. A span is one unit of work: a single operation, with a name, a start, and a duration. The trace includes instrumented tool activity.

Goose sends this data using the OpenTelemetry Protocol (OTLP), the standard wire format Logfire uses to receive telemetry. The same configuration works for the desktop application and CLI, provided the process that starts Goose has the required environment variables.

## Configure Goose

Create a [project write token](../../how-to-guides/create-write-tokens.md). Add the Logfire base URL to the Goose `config.yaml` file:

```yaml
otel_exporter_otlp_endpoint: "https://logfire-us.pydantic.dev"
```

The settings file is at `~/.config/goose/config.yaml` on macOS and Linux, or `%APPDATA%\Block\goose\config\config.yaml` on Windows.

Set the authorization header in the environment that starts Goose:

=== "macOS and Linux"

    ```bash
    export OTEL_TRACES_EXPORTER=otlp
    export OTEL_METRICS_EXPORTER=none
    export OTEL_LOGS_EXPORTER=none
    export OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf
    export OTEL_EXPORTER_OTLP_HEADERS='Authorization=<your-write-token>'
    ```

=== "Windows PowerShell"

    ```powershell
    $env:OTEL_TRACES_EXPORTER = 'otlp'
    $env:OTEL_METRICS_EXPORTER = 'none'
    $env:OTEL_LOGS_EXPORTER = 'none'
    $env:OTEL_EXPORTER_OTLP_PROTOCOL = 'http/protobuf'
    $env:OTEL_EXPORTER_OTLP_HEADERS = 'Authorization=<your-write-token>'
    ```

For an EU project, use `https://logfire-eu.pydantic.dev` in `config.yaml`. These settings use OTLP over HTTP, keep this guide focused on traces, and turn off Goose's optional metric and log sending. Restart Goose after changing the setting or environment.

!!! warning "Keep the token out of the settings file"
    Goose configuration files can be shared or backed up. Store the write token in a secret environment setting instead.

!!! warning "Review session and tool data"
    Goose traces can contain session, user, host, prompt, and tool information. Review this data before enabling tracing. The Logfire SDK's scrubbing feature does not process telemetry sent directly by Goose.

## Verify

Start a new Goose session and make a tool call, then open the [Live view](../../guides/web-ui/live.md). Filter for `service_name = 'goose'` if needed. You should see a trace for the session with child spans for instrumented activity.

## Troubleshooting

| Symptom | Cause and fix |
| --- | --- |
| No traces arrive | Confirm the endpoint is present in the active Goose settings file and the header is in the Goose process environment. |
| Authentication fails | Use `Authorization=<your-write-token>` without a `Bearer` prefix and select the matching regional URL. |
| A changed environment variable has no effect | Fully restart the desktop application or start a new CLI process from the updated shell. |

See [Goose configuration files](https://goose-docs.ai/docs/guides/config-files/) and [observability environment variables](https://goose-docs.ai/docs/guides/environment-variables/#observability) for supported settings and environment precedence.
