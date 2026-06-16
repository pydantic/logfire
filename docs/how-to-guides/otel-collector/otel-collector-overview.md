---
title: "Logfire OTel Collector Configuration & Setup Guide"
description: "Detailed configuration instructions for connecting Logfire to the OpenTelemetry Collector, plus overview of use cases and benefits."
---
# OpenTelemetry Collector

The OpenTelemetry Collector is a powerful tool that can be used to collect, process, and export telemetry data from various sources.
It is designed to work with a wide range of data sources and can be easily configured to meet your specific needs.
It can be run in a multitude of topologies, including as a standalone service, as a sidecar in a container, or as an agent on a host.

Although it is very powerful and versatile the Collector is also an advanced tool that is not required to use Logfire.
If you don't need any of the Collector's features it is perfectly reasonable to send data from the Logfire SDK directly to our backend, and this is the default configuration for our SDK.

Use cases for the OpenTelemetry Collector include:

- **Centralized configuration**: keep Logfire credentials in a single place. Configure exporting to multiple backends (e.g. Logfire and audit logging) in a single place. All with the ability to update the configuration without needing to make changes to applications.
- **Data transformation**: transform data before sending it to Logfire. For example, you can use the OpenTelemetry Collector to filter out sensitive information, extract structured data from logs or otherwise modify the data before sending it to Logfire.
    - For a detailed guide on common transformation patterns, see our guide on [Advanced Scrubbing](otel-collector-scrubbing.md) with the OTel Collector.
- **Data enrichment**: add additional context to your data before sending it to Logfire. For example, you can attach host, container, or Kubernetes metadata so every span and metric carries the same labels.
- **Collecting existing data sources**: the Collector can be used to collect host metrics, Kubernetes cluster state, container logs, and metrics from other formats — all without changing any application code.
- **Long-term archive**: fan out telemetry to durable storage (e.g. AWS S3) in parallel with Logfire so you can retain raw data beyond Logfire's retention window.

As Logfire is a fully compliant OpenTelemetry SDK and backend it does not require any special configuration to be used with the OpenTelemetry Collector.
For more information on the Collector itself please see the [official documentation](https://opentelemetry.io/docs/collector/).

## Guides

This section is task-oriented: pick the scenario you're working on.

- [**Host Monitoring**](host-monitoring.md) — ship CPU, memory, disk, filesystem, network, and process metrics from any host to Logfire using the `hostmetrics` receiver. No SDK or application changes required; the host shows up on the Hosts page.
- [**Kubernetes Monitoring**](kubernetes-monitoring.md) — collect cluster-level state, per-node and per-pod metrics, pod logs, and Kubernetes resource attributes (`k8s.cluster.name`, `k8s.namespace.name`, `k8s.pod.name`, ...). Covers the recommended two-Collector pattern (Deployment + DaemonSet), RBAC, and the `k8sattributesprocessor` for enriching traces from your applications.
- [**Back up data in AWS S3**](s3-backup.md) — fan out telemetry to both Logfire and an S3 bucket so you can retain raw data beyond Logfire's retention window, with notes on partitioning, IAM least-privilege, encryption, and reading the data back.
- [**Advanced Scrubbing**](otel-collector-scrubbing.md) — centralize sensitive-data scrubbing in the Collector so every application sending to it inherits the same redaction rules.
