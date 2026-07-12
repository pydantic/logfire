---
title: "Instrument Airflow: send task traces and metrics"
description: "Turn on Airflow's built-in OpenTelemetry support to send its task traces and metrics to Logfire."
integration: "built-in"
---
# Airflow

See every task your [Airflow][airflow] pipelines run (how long each took and how it ended), plus
Airflow's own metrics, in Logfire. Each task run becomes a **span** (one unit of work with a name, a
start, and a duration), and related spans link into a **trace** (the full journey of one run), so you
can follow a run across your pipeline.

Airflow has native OpenTelemetry support for [traces] and [metrics]: it builds an internal exporter
(the piece that sends telemetry out) and ships data straight to the backend you point it at. So
instead of a `logfire.instrument_*` call, you turn Airflow's own support on and aim it at Logfire with
a couple of settings.

## What you'll capture

- Each task run as a span, with its duration and outcome
- The full run of a pipeline as a trace
- Airflow's built-in metrics

## Before you start

You'll need a Logfire project and its **write token**: the credential Airflow uses to send data to
Logfire. Create a project and copy its token from **Project → Settings → Write tokens** in the
Logfire web app. New to Logfire? Start with [Getting Started](../../index.md), which walks through
creating a project.

!!! warning "Airflow 2.10.4 or newer"
    The setup below needs `apache-airflow` 2.10.4 or later. On older versions you can't set the
    `OTEL_EXPORTER_OTLP_HEADERS` environment variable (a bug the Logfire team fixed in
    [apache/airflow#44346](https://github.com/apache/airflow/pull/44346)). Use the
    [OpenTelemetry Collector](#older-airflow-via-an-opentelemetry-collector) route instead.

## Installation

Airflow has no separate Logfire extra: its OpenTelemetry support is built in. This page configures
Airflow directly, so you don't need to install `logfire` in your Airflow environment. Everything below
is set through environment variables and `airflow.cfg`.

## Usage

Two steps: pass your write token as an OpenTelemetry header, then point Airflow's `otel_*` settings at
Logfire.

First, set the header so Airflow authenticates to Logfire. Run this in the same shell (or set it in the
environment) where Airflow runs, with `LOGFIRE_TOKEN` holding your [write token][write-token]:

```bash
export OTEL_EXPORTER_OTLP_HEADERS="Authorization=${LOGFIRE_TOKEN}"
```

Then turn on OpenTelemetry in your `airflow.cfg` and aim it at Logfire's endpoint:

```ini title="airflow.cfg"
[metrics]
otel_on = True
; use logfire-eu.pydantic.dev for the EU region
otel_host = logfire-us.pydantic.dev
otel_port = 443
otel_prefix = airflow
otel_interval_milliseconds = 30000  # The interval between exports, defaults to 60000
otel_ssl_active = True

[traces]
otel_on = True
; use logfire-eu.pydantic.dev for the EU region
otel_host = logfire-us.pydantic.dev
otel_port = 443
otel_prefix = airflow
otel_ssl_active = True
otel_task_log_event = True
```

For the full list of settings, see Airflow's [traces] and [metrics] documentation.

## Verify it worked

Trigger a pipeline run, then open the [Live view](../../guides/web-ui/live.md). Within a few seconds
you'll see spans for the task runs: click one to see its duration and outcome. Airflow's metrics
appear in your project's dashboards.

<!-- TODO(app-verify): screenshot of an Airflow task span in the Live view, showing the task name and duration -->

## Troubleshooting

Not seeing your task runs? Check that `OTEL_EXPORTER_OTLP_HEADERS` is set in the environment Airflow
actually runs in, that `LOGFIRE_TOKEN` holds a valid write token, that `otel_on = True` under both
`[traces]` and `[metrics]`, and that `otel_host` matches your region (`logfire-us.pydantic.dev` or
`logfire-eu.pydantic.dev`). On `apache-airflow` older than 2.10.4, use the Collector route below.

## Advanced

### Older Airflow: via an OpenTelemetry Collector

If your `apache-airflow` is older than 2.10.4, you can't set the `OTEL_EXPORTER_OTLP_HEADERS`
environment variable, so Airflow can't authenticate to Logfire directly. Instead, run an
[OpenTelemetry Collector] (a standalone agent that receives telemetry from your apps and forwards it
on) in front of Logfire. Airflow sends to the collector; the collector adds your token and forwards
to Logfire.

!!! note
    A collector is also handy when you already send data to another backend and want to try Logfire
    alongside it: point the collector at both, compare, and switch over once you're happy.

Follow the [OpenTelemetry Collector installation] guide to set one up, then use this configuration:

```yaml title="otel-collector-config.yaml"
receivers:  # (1)!
  otlp:
    protocols:
      grpc:
        endpoint: "0.0.0.0:4317"
      http:
        endpoint: "0.0.0.0:4318"

exporters:  # (2)!
  debug:  # (3)!
  otlphttp:
    endpoint: https://logfire-us.pydantic.dev/  # or https://logfire-eu.pydantic.dev/ for the EU region
    compression: gzip
    headers:
      Authorization: "Bearer ${env:LOGFIRE_TOKEN}"  # (4)!

processors:
  batch:
    timeout: 1s
    send_batch_size: 32768

extensions:
  health_check:
    endpoint: "0.0.0.0:13133"

service:  # (5)!
  extensions: [health_check]
  pipelines:
    traces:
      receivers: [otlp]
      processors: [batch]
      exporters: [debug, otlphttp]
    metrics:
      receivers: [otlp]
      processors: [batch]
      exporters: [debug, otlphttp]
```

1. Receivers collect data from your applications.

    See the [OpenTelemetry Collector Receiver] section for more.

2. Exporters send data on. The `otlphttp` exporter sends it to Logfire.

3. The `debug` exporter prints what's being sent to the console: useful while setting things up, and
   safe to remove in production.

4. The `Authorization` header carries your Logfire write token. `${env:LOGFIRE_TOKEN}` is replaced by
   the environment variable of the same name.

5. The service section wires up the pipelines: `traces` for trace data, `metrics` for metrics.

Then point Airflow at the collector (running locally, no TLS) in your `airflow.cfg`:

```ini title="airflow.cfg"
[metrics]
otel_on = True
otel_host = localhost
otel_port = 4318
otel_prefix = airflow
otel_interval_milliseconds = 30000  # The interval between exports, defaults to 60000
otel_ssl_active = False

[traces]
otel_on = True
otel_host = localhost
otel_port = 4318
otel_prefix = airflow
otel_ssl_active = False
otel_task_log_event = True
```

## Reference

- [Airflow traces configuration][traces] and [metrics configuration][metrics]: the official docs.
- [OpenTelemetry Collector][OpenTelemetry Collector]: for the older-Airflow route.

[airflow]: https://airflow.apache.org/
[traces]: https://airflow.apache.org/docs/apache-airflow/stable/administration-and-deployment/logging-monitoring/traces.html
[metrics]: https://airflow.apache.org/docs/apache-airflow/stable/administration-and-deployment/logging-monitoring/metrics.html#setup-opentelemetry
[OpenTelemetry Collector]: https://opentelemetry.io/docs/collector/
[OpenTelemetry Collector installation]: https://opentelemetry.io/docs/collector/installation/
[OpenTelemetry Collector Receiver]: https://opentelemetry.io/docs/collector/configuration/#receivers
[write-token]: ../../how-to-guides/create-write-tokens.md
