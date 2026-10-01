---
title: "Understand the OpenTelemetry Collector"
description: "What the OpenTelemetry Collector does, when you need one with Logfire, and how a Collector configuration is put together."
---
# OpenTelemetry Collector

Send data to Logfire from places your application code cannot reach, and change what you send by editing one file instead of redeploying every service.

[OpenTelemetry](https://opentelemetry.io/) is the open industry standard for collecting traces, metrics, and logs. The **OpenTelemetry Collector** is a separate program built around it that sits between your apps and Logfire: your applications send to the Collector, and the Collector sends on to Logfire.

Logfire receives standard OpenTelemetry data, so nothing here is Logfire-specific apart from the endpoint and the token.

## When you need one

Most projects do not. The Logfire SDK sends straight to Logfire, which is the default and means one less program to run and monitor. Start there.

Add a Collector when you want to:

- **Collect data that has no SDK.** Host metrics, Kubernetes cluster state, container logs, and Prometheus endpoints all become available without touching application code.
- **Keep credentials and rules in one place.** [Write tokens](../create-write-tokens.md), redaction rules, and sampling policy live in one configuration file instead of in every service.
- **Change what you send without a redeploy.** Filtering, enrichment, and routing become configuration rather than code.
- **Send the same data to more than one destination**, such as Logfire plus long-term storage in Amazon S3.

If none of those apply, send straight from the SDK and come back when one does.

## How a configuration is put together

Every Collector configuration has the same four blocks:

```yaml title="otel-collector-config.yaml"
receivers:   # where data comes in
processors:  # what happens to it on the way through (optional)
exporters:   # where it goes
service:
  pipelines: # which receivers feed which processors feed which exporters
```

A receiver, processor, or exporter you define but do not list in a pipeline does nothing at all. That is the most common reason a configuration that looks correct sends no data. Extensions are the exception: they are activated under `service.extensions` instead.

Pipelines are per signal. Traces, metrics, and logs each get their own, and they can share components:

```yaml title="otel-collector-config.yaml"
receivers:
  otlp:
    protocols:
      http:
        endpoint: 0.0.0.0:4318
  hostmetrics:
    collection_interval: 60s
    scrapers:
      cpu:

processors:
  batch:

exporters:
  otlphttp:
    endpoint: "https://logfire-us.pydantic.dev"
    headers:
      Authorization: "Bearer ${env:LOGFIRE_TOKEN}"

service:
  pipelines:
    traces:
      receivers: [otlp]        # traces arrive from your apps
      processors: [batch]
      exporters: [otlphttp]
    metrics:
      receivers: [hostmetrics] # metrics are read off the machine
      processors: [batch]
      exporters: [otlphttp]
```

## The Logfire exporter

Wherever a guide in this section sends data to Logfire, it ends in the same exporter block:

```yaml title="otel-collector-config.yaml"
exporters:
  otlphttp:
    endpoint: "https://logfire-us.pydantic.dev"  # or https://logfire-eu.pydantic.dev
    headers:
      Authorization: "Bearer ${env:LOGFIRE_TOKEN}"
```

The one exception in this section is the [S3 backup guide](s3-backup.md), where the Collector writes only to S3 and the SDK keeps sending to Logfire itself.

Two things have to match your project:

- **The endpoint must match the [data region](../../reference/data-regions.md) your project lives in**, `logfire-us` or `logfire-eu`. A write token works only against its own region.
- **The token is a write token**, the credential a deployed app uses to send data to a Logfire project. Pass it through the environment rather than writing it into the file.

The Collector appends `/v1/traces`, `/v1/metrics`, and `/v1/logs` to that endpoint on its own.

!!! note
    Newer Collector versions warn at startup that the `otlphttp` exporter name is deprecated in favor of `otlp_http`. Both names work. These guides use `otlphttp` so that one name is used across the whole set.

## Should the SDK still send to Logfire directly?

[Send data through a Collector](send-data-through-a-collector.md) shows how to point an application at one. The decision that guide cannot make for you is whether the application should *also* keep sending to Logfire itself.

`send_to_logfire=False` makes the Collector the only path out. Leave it `True` and the application sends its own copy as well, so anything the Collector changed arrives alongside the version it changed, and you pay for both. Keep it set to `True` when you want the Collector to handle an extra destination while normal data keeps flowing directly, as in the [S3 backup guide](s3-backup.md). Set it to `False` whenever the Collector changes the data, so that Logfire receives the changed version rather than both.

## Guides

Start with [**Send data through a Collector**](send-data-through-a-collector.md). It gets the smallest working setup running in a few minutes, and every other guide here builds on it.

Then, as you need them:

- [**Host monitoring**](host-monitoring.md): ship CPU, memory, disk, filesystem, network, and process metrics from any host to Logfire using the `hostmetrics` receiver. No SDK or application changes required; the host shows up on the Hosts page.
- [**Kubernetes monitoring**](kubernetes-monitoring.md): install the recommended Helm stack to collect cluster-level state, per-node and per-pod metrics, pod logs, and Kubernetes resource attributes (`k8s.cluster.name`, `k8s.namespace.name`, `k8s.pod.name`, ...). If you need to own the manifests, use the [custom Collector setup](kubernetes-manual-setup.md).
- [**Control volume and cost**](control-volume-and-cost.md): drop the traffic you never look at and keep the traces that matter, so your bill tracks the value you get rather than the traffic you receive.
- [**Route traces to different Logfire projects**](route-to-multiple-projects.md): send each request to whichever project it belongs to, chosen while the request runs, so one deployment can feed a project per customer or per environment.
- [**Scrub sensitive data**](otel-collector-scrubbing.md): centralize sensitive-data scrubbing in the Collector so every application sending to it inherits the same redaction rules.
- [**Collect cloud provider metrics**](../cloud-metrics.md): pull metrics from Google Cloud and AWS through the Collector, with deployment examples for Cloud Run and ECS.
- [**Back up data in AWS S3**](s3-backup.md): fan out telemetry to both Logfire and an S3 bucket so you can retain raw data beyond Logfire's retention window, with notes on partitioning, IAM least-privilege, encryption, and reading the data back.

For the Collector itself, see the [official documentation](https://opentelemetry.io/docs/collector/).
