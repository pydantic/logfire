---
title: "Send n8n workflow traces to Logfire"
description: "Configure n8n OpenTelemetry tracing to send workflow, node, and agent spans to Pydantic Logfire."
integration: otel
---

# Send n8n workflow traces to Logfire

See each n8n workflow execution as a trace (the full journey of one workflow run, made of one or more spans) in Logfire. A span is one unit of work: a single operation, with a name, a start, and a duration. n8n can include one child span for every node execution.

n8n sends traces using the OpenTelemetry Protocol (OTLP), the standard wire format Logfire uses to receive telemetry. OTLP tracing over HTTP is available starting in n8n 2.19.0. Agent tracing is available starting in n8n 2.33.0; OpenTelemetry-formatted metrics are not yet supported.

!!! warning "Agent traces can contain conversation data"
    On n8n 2.33.0 and later, agent traces can contain prompts, tool arguments, responses, and tool results. The Logfire SDK's scrubbing feature does not process telemetry sent directly by n8n. Use the n8n content controls below before tracing production agents.

## Configure n8n in the user interface

In n8n 2.27.0 or later, an instance owner or administrator can open **Settings → OpenTelemetry** and enter the following values. This route does not require access to the n8n runtime environment.

| Setting | Value |
| --- | --- |
| Enable OpenTelemetry | On |
| OTLP endpoint | `https://logfire-us.pydantic.dev` |
| Tracing path | `/v1/traces` |
| Headers | `authorization=<your-write-token>` |
| Service name | `n8n` |
| Include node spans | On |

Create the token in [Logfire project settings](../../how-to-guides/create-write-tokens.md). For an EU project, use `https://logfire-eu.pydantic.dev`. Select **Send test trace**, confirm that n8n reports success, then save the settings. n8n reloads user-interface changes across queue workers and webhook processors.

If **Settings → OpenTelemetry** is not present in a hosted workspace, that workspace does not expose this direct OTLP route.

## Configure n8n with environment variables

For a deployment whose runtime you control, use n8n 2.19.0 or later and set these variables on the main instance, queue workers, and webhook processors:

```dotenv
N8N_OTEL_ENABLED=true
N8N_OTEL_EXPORTER_OTLP_ENDPOINT=https://logfire-us.pydantic.dev
N8N_OTEL_EXPORTER_OTLP_HEADERS=authorization=<your-write-token>
N8N_OTEL_EXPORTER_SERVICE_NAME=n8n
N8N_OTEL_TRACES_INCLUDE_NODE_SPANS=true
```

n8n appends `/v1/traces` by default. Restart the affected instances after applying environment settings. Environment variables take precedence over matching values saved in the user interface.

By default, n8n 2.25.2 and later exports only production executions of published workflows. To include manual and test executions, set:

```dotenv
N8N_OTEL_TRACES_PRODUCTION_ONLY=false
```

## Control agent content

Agent spans are enabled by default in n8n 2.33.0 and later when OpenTelemetry is enabled. They can contain prompts, tool arguments, responses, and tool results. To keep the spans but omit input and output content, set:

```dotenv
N8N_AGENTS_TRACING_RECORD_INPUTS=false
N8N_AGENTS_TRACING_RECORD_OUTPUTS=false
```

To disable agent spans entirely, set `N8N_AGENTS_TRACING_ENABLED=false`.

## Verify

Run a published workflow as a production execution, then open the [Live view](../../guides/web-ui/live.md). You should see a `workflow.execute` span containing `node.execute` child spans. A successful test trace from the settings page proves connectivity, but it does not prove that the workflow qualifies for tracing.

## Troubleshooting

| Symptom | Cause and fix |
| --- | --- |
| Test trace succeeds but a manual run is missing | Run a production execution, or set `N8N_OTEL_TRACES_PRODUCTION_ONLY=false` on n8n 2.25.2 or later. |
| Workflow appears without node spans | Ensure **Include node spans** is on or `N8N_OTEL_TRACES_INCLUDE_NODE_SPANS=true`. |
| Data arrives from only some executions | Apply the same settings to every main, worker, and webhook instance in queue mode. |
| Authentication fails | Use `authorization=<your-write-token>` without a `Bearer` prefix and select the token's Logfire region. |
| Agent spans are missing | Agent tracing requires n8n 2.33.0 or later, `N8N_OTEL_ENABLED=true`, and `N8N_AGENTS_TRACING_ENABLED` not set to `false`. |

See [n8n OpenTelemetry tracing](https://docs.n8n.io/deploy/host-n8n/keep-n8n-running/trace-executions-with-opentelemetry) and its [environment variable reference](https://docs.n8n.io/deploy/host-n8n/configure-n8n/basic-configuration/use-environment-variables/opentelemetry) for the versioned settings.
