---
title: "Send OpenRouter Broadcast traces to Logfire"
description: "Configure OpenRouter Broadcast to send model-request traces directly to Pydantic Logfire over the OpenTelemetry Protocol."
integration: otel
---

# Send OpenRouter Broadcast traces to Logfire

See each request made through OpenRouter as a trace (the full journey of one request, made of one or more spans) in Logfire without adding instrumentation to your application. A span is one unit of work: a single operation, with a name, a start, and a duration.

OpenRouter Broadcast sends these traces using the OpenTelemetry Protocol (OTLP), the standard wire format Logfire uses to receive telemetry.

This integration captures OpenRouter activity, including model and provider selection, input and output messages, token usage, cost, timing, and tool-call metadata. It does not capture the surrounding agent steps, application code, database calls, or other services. Instrument those components separately when you need an end-to-end trace.

## Configure OpenRouter Broadcast

Create a [Logfire project write token](../../how-to-guides/create-write-tokens.md). Then, in the OpenRouter dashboard:

1. Open **Settings → Observability**.
2. Turn on **Enable Broadcast**.
3. Add the **OpenTelemetry Collector** destination.
4. Enter the full traces endpoint for your Logfire [data region](../../reference/data-regions.md):

    === "US"

        ```text
        https://logfire-us.pydantic.dev/v1/traces
        ```

    === "EU"

        ```text
        https://logfire-eu.pydantic.dev/v1/traces
        ```

5. Enter the Logfire authorization header as a JSON object:

    ```json
    {
      "Authorization": "<your-write-token>"
    }
    ```

    Use the raw write token without a `Bearer` prefix.

6. Select **Test Connection**, then save the destination.

Despite its name in OpenRouter, the **OpenTelemetry Collector** destination can send directly to any compatible OTLP/HTTP backend. You do not need to deploy a Collector for this setup. OpenRouter sends traces using OTLP/HTTP with JSON encoding.

## Control which data is sent

By default, Broadcast can include prompts and model responses. Before sending production traffic:

- Turn on **Privacy Mode** for the destination to exclude input messages and model outputs while retaining token counts, cost, timing, model information, and custom metadata. Privacy Mode does not remove the optional `user`, `session_id`, or `trace` fields, so omit sensitive values from those fields separately.
- Set a sampling rate to control the proportion of traces sent. Start with `1.0` while verifying the connection, then reduce it if needed for traffic volume or cost.
- Select specific OpenRouter API keys if the destination should receive traces from only part of your OpenRouter traffic.

!!! warning "Review model and user data"
    Privacy Mode removes prompts and responses, but it does not remove tool information, user identifiers, session identifiers, or custom metadata. Review this data before enabling Broadcast for production traffic, and omit fields that must not leave OpenRouter. The Logfire SDK's scrubbing feature does not process telemetry sent directly by OpenRouter.

## Add trace context

OpenRouter can attach more context when a request includes its optional `user`, `session_id`, or `trace` fields. The reserved `trace_id` and `parent_span_id` keys set trace context, while `trace_name`, `span_name`, and `generation_name` set span names. Other values in the `trace` object become span attributes under `trace.metadata.*`, which you can use to filter or group records in Logfire.

For example:

```json
{
  "model": "openai/gpt-4o",
  "messages": [{"role": "user", "content": "Summarize this document"}],
  "user": "user_12345",
  "session_id": "session_abc",
  "trace": {
    "environment": "production",
    "feature": "document-summary"
  }
}
```

Do not put secrets or unnecessary personal data in these fields.

## Verify

Make a model request through an OpenRouter API key included in the destination, then open the [Live view](../../guides/web-ui/live.md). Filter for `service_name = 'openrouter'` if needed. Broadcast sends traces asynchronously after requests finish, so they may appear shortly after the response completes.

## Troubleshooting

| Symptom | Cause and fix |
| --- | --- |
| **Test Connection** fails | Confirm the endpoint includes `/v1/traces`, the regional URL matches the Logfire project, and the `Authorization` header contains a valid project write token. |
| The test succeeds but no model requests appear | Confirm Broadcast is enabled, the destination is saved, its sampling rate is greater than zero, and the OpenRouter API key used by the request is included in the destination filter. |
| Prompts or responses are missing | OpenRouter Privacy Mode removes this content before export. Turn it off only after reviewing the data-handling implications. |
| OpenRouter spans are separate from application traces | Broadcast covers OpenRouter requests only. Instrument the application as well, and add shared identifiers as trace metadata when you need to find related records. |

See the OpenRouter documentation for [Broadcast](https://openrouter.ai/docs/guides/features/broadcast) and its [OpenTelemetry Collector destination](https://openrouter.ai/docs/guides/features/broadcast/otel-collector).
