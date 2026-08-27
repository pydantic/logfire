---
title: "Migrate to Logfire from another OpenTelemetry backend"
description: "Already sending OpenTelemetry data to Datadog, Grafana, Honeycomb, or another vendor? Migrate to Logfire by repointing your exporter — no re-instrumentation, no application code changes."
---

# Migrate to Logfire

Logfire is a fully compliant [OpenTelemetry](https://opentelemetry.io/) backend. If your services already emit OpenTelemetry data — from OTel SDKs, from a Collector distribution such as [Grafana Alloy](grafana.md), the [Splunk](splunk.md) or [Datadog](datadog.md) distro, [ADOT](aws.md), or [EDOT](elastic.md), or from a vendor agent's OTLP intake — you already did the hard part. Migrating to Logfire means **repointing the exporter**, not re-instrumenting your applications.

Nothing about your instrumentation changes: the same spans, metrics, and logs your code already produces are sent to Logfire instead of (or as well as) your current vendor. There is no proprietary agent and no Logfire-specific SDK requirement — the standard OpenTelemetry exporter is all you need.

## What you need

- **A Logfire project and its write token.** The write token is the credential that selects the destination project and authorizes writes. Create one under **Project → Settings → Write tokens** (see [Create Write Tokens](../how-to-guides/create-write-tokens.md)). Treat it like a password: set it from an environment variable, never commit it.
- **Your data region's endpoint:**
    - US: `https://logfire-us.pydantic.dev`
    - EU: `https://logfire-eu.pydantic.dev`

  Every example below uses the US endpoint; swap in the EU one if your project lives there. See [Data regions](../reference/data-regions.md).

## The two paths

However your telemetry reaches your current vendor, one of these two changes points it at Logfire instead.

### Path A — OTel SDKs (or any OTLP exporter)

If your applications export OTLP directly (via the OpenTelemetry SDK's environment variables, or a vendor SDK built on OTel), set three variables:

```sh
export OTEL_EXPORTER_OTLP_ENDPOINT=https://logfire-us.pydantic.dev
export OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf
export OTEL_EXPORTER_OTLP_HEADERS='Authorization=your-write-token'
# optional but recommended, so your service isn't grouped under "(unknown)":
export OTEL_SERVICE_NAME=your-service-name
```

That's the whole change. See [Alternative clients](../how-to-guides/alternative-clients.md) for worked Python, Node.js, and Rust examples.

!!! note "Agent-side processing"
    If your telemetry currently flows through a vendor agent or Collector that samples, filters, enriches, or scrubs it, sending straight from an SDK skips that processing. Keep an OpenTelemetry Collector in the path (Path B), with the same processors, if you rely on it.

### Path B — the OpenTelemetry Collector (any distribution)

If you run a Collector — the upstream `otelcol`, or a vendor distribution like Alloy, ADOT, EDOT, or the Splunk/Datadog distros — add an `otlphttp` exporter that targets Logfire and reference it from each pipeline:

```yaml
exporters:
  otlphttp/logfire:
    endpoint: "https://logfire-us.pydantic.dev"  # or https://logfire-eu.pydantic.dev
    headers:
      Authorization: "Bearer ${env:LOGFIRE_TOKEN}"

service:
  pipelines:
    traces:
      exporters: [otlphttp/logfire]
    metrics:
      exporters: [otlphttp/logfire]
    logs:
      exporters: [otlphttp/logfire]
```

Your receivers and processors don't change. See the [OpenTelemetry Collector](../how-to-guides/otel-collector/otel-collector-overview.md) guide for the full picture.

!!! note "HTTP or gRPC"
    Logfire's managed platform accepts OTLP over both **HTTP** and **gRPC**. These examples use HTTP (`http/protobuf`) because every OpenTelemetry SDK and Collector supports it out of the box.

## Cut over without a gap

Because an OpenTelemetry pipeline can fan out to more than one destination, you don't have to switch in one step. Keep your existing exporter and add Logfire alongside it, then compare the same traffic in both backends before you remove the old one:

```yaml
service:
  pipelines:
    traces:
      exporters: [otlphttp/your-current-vendor, otlphttp/logfire]
```

Run in parallel for as long as you like, rebuild the dashboards and alerts you rely on in Logfire, then drop the old exporter.

## What changes, and what doesn't

| Stays the same | You rebuild in Logfire |
| --- | --- |
| Your instrumentation (SDKs, auto-instrumentation, semantic conventions) | Dashboards |
| The spans, metrics, and logs you already emit | Alerts |
| Your Collector receivers and processors | Saved queries / monitors |

Instrumentation is portable because it's OpenTelemetry; dashboards and alerts are vendor-specific by nature, so those are recreated once against Logfire. Logfire queries everything with SQL (PostgreSQL-compatible), so a saved query is a SQL statement rather than a proprietary expression.

## Per-vendor guides

- [Datadog](datadog.md)
- [Grafana Cloud / Grafana Alloy](grafana.md)
- [Honeycomb](honeycomb.md)
- [New Relic](new-relic.md)
- [Dynatrace](dynatrace.md)
- [Splunk Observability Cloud](splunk.md)
- [Elastic](elastic.md)
- [AWS (ADOT → CloudWatch / X-Ray)](aws.md)

Using a backend that isn't listed? If it speaks OTLP, the two paths above still apply — point the exporter at Logfire.

## Verify

Run your workload, then open the [Live view](../guides/web-ui/live.md) for your project. New traces should appear within a few seconds. If nothing shows up, confirm the write token is set and the endpoint matches your data region.
