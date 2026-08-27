---
title: "Connect no-code AI platforms to Logfire with OTLP"
description: "Configure no-code AI and workflow platforms that export OpenTelemetry data to Pydantic Logfire."
---

# Connect no-code AI platforms to Logfire with OTLP

Send the telemetry a platform exposes to Logfire, then inspect it alongside the rest of your system. A trace is the full journey of one request or agent run, made of one or more spans. A span is one unit of work: a single operation, with a name, a start, and a duration. A metric is a number tracked over time, like requests per second or CPU load.

Every platform listed here can send data using the OpenTelemetry Protocol (OTLP), the standard wire format Logfire uses to receive telemetry. Some send detailed traces, while Flowise currently sends metrics only.

The guides distinguish settings available in a hosted product's user interface from settings that require control of the process that runs the product.

The configuration location matters. A **runtime configuration** row means you need access to the deployment's environment variables; it does not imply that the vendor's hosted service exposes those variables. Products that only provide an internal trace viewer, an API for querying stored traces, or downloadable trace data are not listed because those features do not provide a live OTLP destination.

## Choose your platform

| Platform | What can be connected | Where it is configured |
| --- | --- | --- |
| [Dify](dify.md) | Application and workflow traces and metrics | Dify runtime configuration |
| [Flowise](flowise.md) | API, flow, and prediction metrics, but not detailed traces or Node.js process metrics | Flowise runtime and an OpenTelemetry Collector |
| [Goose](goose.md) | Agent-session and tool traces | Local settings and environment |
| [Langflow](langflow.md) | Flow, model, and tool traces | Langflow runtime configuration |
| [LobeChat](lobe-chat.md) | Request, model, agent, tool traces, and metrics | LobeChat runtime configuration |
| [n8n](n8n.md) | Workflow and node traces; agent traces on newer versions | **Settings** in supported hosted workspaces, or runtime configuration |
| [Open WebUI](open-webui.md) | HTTP, database, and cache traces, metrics, and logs | Open WebUI runtime and an OpenTelemetry Collector |

## Use the Logfire OTLP values

Create a [project write token](../../how-to-guides/create-write-tokens.md). Use the base URL for the [data region](../../reference/data-regions.md) that stores your project:

| Region | Base URL |
| --- | --- |
| US | `https://logfire-us.pydantic.dev` |
| EU | `https://logfire-eu.pydantic.dev` |

The platform guides show whether to supply the base URL or a signal-specific path such as `/v1/traces`. They also show the header syntax expected by that platform. Do not add `Bearer` unless the guide includes it.

!!! warning "Telemetry can include user and model data"
    Traces can contain prompts, model responses, tool arguments, tool results, or other user data. Review each platform's capture controls before enabling telemetry for production traffic. The Logfire SDK's [scrubbing](../../how-to-guides/scrubbing.md) feature does not process telemetry that these platforms send directly, so exclude or redact sensitive content at the source.

Keep the write token in an administrator-only secret or environment setting. Do not put it in a workflow variable, prompt, custom tool, or browser-side setting.
