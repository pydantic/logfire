---
title: "Understand the OpenTelemetry Collector"
description: "What the OpenTelemetry Collector does, when you need one with Logfire, and how a Collector configuration is put together."
---
# OpenTelemetry Collector

Send data to Logfire from places your application code cannot reach, and change what you send by editing one file instead of redeploying every service.

The **OpenTelemetry Collector** is a separate program that sits between your apps and Logfire, gathering telemetry and forwarding it. Your applications send to the Collector, and the Collector sends to Logfire.

Logfire is a standard OpenTelemetry backend, so it needs no special handling. Any Collector build can send to it.

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

A component you define but do not list in a pipeline does nothing at all. That is the most common reason a configuration that looks correct sends no data.

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

Every guide in this section ends in the same exporter block:

```yaml title="otel-collector-config.yaml"
exporters:
  otlphttp:
    endpoint: "https://logfire-us.pydantic.dev"  # or https://logfire-eu.pydantic.dev
    headers:
      Authorization: "Bearer ${env:LOGFIRE_TOKEN}"
```

Two things have to match your project:

- **The endpoint must match the region your project lives in**, `logfire-us` or `logfire-eu`. A write token works only against its own region.
- **The token is a write token**, the credential a deployed app uses to send data to a Logfire project. Pass it through the environment rather than writing it into the file.

The Collector appends `/v1/traces`, `/v1/metrics`, and `/v1/logs` to that endpoint on its own.

## Sending from the SDK to the Collector

Point the SDK at the Collector, and decide whether it should also keep sending straight to Logfire:

```python
import os

os.environ['OTEL_EXPORTER_OTLP_ENDPOINT'] = 'http://collector:4318'

import logfire

logfire.configure(send_to_logfire=False)
```

`send_to_logfire=False` makes the Collector the only path out. Keep it set to `True` when you want the Collector to handle an extra destination while normal data keeps flowing directly, as in the [S3 backup guide](s3-backup.md). Set it to `False` whenever the Collector changes the data, so that Logfire receives the changed version rather than both.

## Guides

- [**Send data through a Collector**](send-data-through-a-collector.md): the smallest working setup, running in a few minutes, so you have something to build on.
- [**Host monitoring**](host-monitoring.md): ship CPU, memory, disk, filesystem, network, and process metrics from any host to Logfire using the `hostmetrics` receiver. No SDK or application changes required; the host shows up on the Hosts page.
- [**Kubernetes monitoring**](kubernetes-monitoring.md): install the recommended Helm stack to collect cluster-level state, per-node and per-pod metrics, pod logs, and Kubernetes resource attributes (`k8s.cluster.name`, `k8s.namespace.name`, `k8s.pod.name`, ...). If you need to own the manifests, use the [custom Collector setup](kubernetes-manual-setup.md).
- [**Control volume and cost**](control-volume-and-cost.md): drop the traffic you never look at and keep the traces that matter, so your bill tracks the value you get rather than the traffic you receive.
- [**Route traces to different Logfire projects**](route-to-multiple-projects.md): send each request to whichever project it belongs to, chosen while the request runs, so one deployment can feed a project per customer or per environment.
- [**Scrub sensitive data**](otel-collector-scrubbing.md): centralize sensitive-data scrubbing in the Collector so every application sending to it inherits the same redaction rules.
- [**Back up data in AWS S3**](s3-backup.md): fan out telemetry to both Logfire and an S3 bucket so you can retain raw data beyond Logfire's retention window, with notes on partitioning, IAM least-privilege, encryption, and reading the data back.

For the Collector itself, see the [official documentation](https://opentelemetry.io/docs/collector/).
