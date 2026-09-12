---
title: Observe services without code changes using OBI
description: "Send request traces and application metrics from OpenTelemetry eBPF Instrumentation directly to Logfire."
---
# Observe services without code changes using OBI

See HTTP and gRPC requests from Linux services without changing their application code. OpenTelemetry
eBPF Instrumentation (OBI) observes supported processes at the operating-system level and sends
the resulting data directly to Logfire. Each span is one unit of work: a single operation, with a
name, a start, and a duration. A trace is the full journey of one request, made of nested spans. A
metric is a number tracked over time, like requests per second or CPU load.

OBI is useful when you cannot add an SDK to a service, or when you want a quick inventory before
adding deeper instrumentation. It does not collect application logs or explain work inside a
request, such as database queries and model calls. Add an OpenTelemetry or Logfire SDK when you
need that detail.

OBI is a pre-release OpenTelemetry project. Its configuration and telemetry can change between
`v0` minor releases, so this guide pins the exact OBI v0.13.0 image tested with Logfire.

## Before you start

You need:

- A Linux host and kernel [supported by OBI](https://opentelemetry.io/docs/zero-code/obi/).
- Permission to inspect the target processes and load extended Berkeley Packet Filter (eBPF)
  programs into the kernel.
- A Logfire project and a write token from **Project settings > Write tokens**.
- The endpoint for your [Logfire data region](../reference/data-regions.md):
  `https://logfire-us.pydantic.dev` for the US or `https://logfire-eu.pydantic.dev` for the EU.

!!! warning "OBI needs host-level access"
    The Docker example uses the host process namespace and privileged mode. This lets OBI inspect
    every process on the host and load eBPF programs. Review OBI's
    [security guidance](https://opentelemetry.io/docs/zero-code/obi/security/) and use its narrower
    capability set before deploying to production.

## Run OBI with Docker Compose

Keep the Logfire write token outside the Compose file:

```bash
export LOGFIRE_TOKEN='your-write-token'
```

Add OBI beside the service you want to observe. This example selects the process that listens on
container port `8080`. It sends both traces and metrics through the OpenTelemetry Protocol (OTLP),
the standard wire format Logfire uses to receive that data:

!!! note "This sends data to Logfire"
    This configuration sends observed request and service metadata to your Logfire project, where
    Logfire stores it according to the project's retention settings. Review the attributes OBI
    captures before enabling it for production traffic.

```yaml
services:
  checkout-api:
    image: your-registry/checkout-api:latest
    environment:
      OTEL_SERVICE_NAME: checkout-api
      OTEL_RESOURCE_ATTRIBUTES: >-
        service.namespace=shop,
        service.version=1.4.0,
        deployment.environment.name=production
    ports:
      - "8080:8080"

  obi:
    image: otel/ebpf-instrument:v0.13.0@sha256:5e89d7478b5feeb8ee73881c58bfe5bb0ccb6dcd4f8cd62e30457aa6e6426adb
    pid: host
    privileged: true
    restart: unless-stopped
    environment:
      OTEL_EBPF_OPEN_PORT: "8080"
      OTEL_EBPF_ENFORCE_SYS_CAPS: "1"
      OTEL_EBPF_SERVICE_NAME: checkout-api
      OTEL_EXPORTER_OTLP_ENDPOINT: https://logfire-us.pydantic.dev
      OTEL_EXPORTER_OTLP_HEADERS: Authorization=${LOGFIRE_TOKEN}
      OTEL_EXPORTER_OTLP_PROTOCOL: http/protobuf
```

Change the endpoint to `https://logfire-eu.pydantic.dev` for an EU project. Start the services and
send traffic to the application:

```bash
docker compose up -d
curl http://localhost:8080/health
```

`OTEL_EBPF_OPEN_PORT` matches the port opened by the process inside its container. If you publish
container port `8080` as host port `18080`, keep the selector set to `8080`.

Set `OTEL_SERVICE_NAME` and the service metadata on each target workload. The
`OTEL_EBPF_SERVICE_NAME` fallback in this single-service example gives OBI the same stable identity
when it cannot read that metadata from a target process. For one OBI instance that observes multiple
services, remove the fallback and configure discovery metadata for each target instead.
Use OBI's [service discovery configuration](https://opentelemetry.io/docs/zero-code/obi/configure/service-discovery/)
when you need to select workloads by executable, container, namespace, or Kubernetes metadata.

## Deploy OBI on Kubernetes

Use the official [OBI Helm chart](https://opentelemetry.io/docs/zero-code/obi/setup/helm/) or
[Kubernetes deployment guide](https://opentelemetry.io/docs/zero-code/obi/setup/kubernetes/).
Run OBI as a DaemonSet, which places one OBI pod on each node, to observe selected workloads across
the cluster. Run it as a sidecar to limit it to one pod.

Configure its exporter from a Kubernetes Secret rather than placing a token in a workload manifest:

```yaml
env:
  - name: OTEL_EXPORTER_OTLP_ENDPOINT
    value: https://logfire-us.pydantic.dev
  - name: OTEL_EXPORTER_OTLP_PROTOCOL
    value: http/protobuf
  - name: OTEL_EXPORTER_OTLP_HEADERS
    valueFrom:
      secretKeyRef:
        name: logfire-otlp
        key: headers
```

Set the `headers` secret value to `Authorization=your-write-token`. Enable OBI's Kubernetes metadata
decoration and use standard workload labels so service names remain stable when pods are replaced.

## Verify the telemetry

Generate several requests, then allow one OBI export interval for the data to arrive.

1. Open **Live** and filter by `service_name = 'checkout-api'`. You should see HTTP or gRPC server
   spans, which are units of work with a start time and duration.
2. Open **Services** and confirm that `checkout-api` appears with recent activity.
3. Open **Explore > Metrics** and run:

```sql
SELECT
  DISTINCT metric_name
FROM metrics
WHERE service_name = 'checkout-api'
  AND metric_name IN ('http.server.request.duration', 'target.info')
ORDER BY metric_name;
```

You should see:

```text
metric_name
--------------------------------
http.server.request.duration
target.info
```

OBI metadata metrics such as `target.info` use the discovered workload's service name and instance
ID even though OBI places that identity on each metric datapoint instead of its enclosing
OpenTelemetry resource.

## Troubleshoot the setup

| Symptom | Cause and fix |
| --- | --- |
| No traces or metrics appear | Check the OBI logs for missing capabilities or an unsupported kernel. Confirm the selected port is the port opened inside the target container, then send traffic after OBI starts. |
| OBI reports `401` or `403` | Use a write token for the intended project and set `OTEL_EXPORTER_OTLP_HEADERS` to `Authorization=your-write-token`. |
| The service appears as `unknown_service` | Set `OTEL_SERVICE_NAME` on the target workload. Add `service.namespace`, `service.version`, and `deployment.environment.name` through `OTEL_RESOURCE_ATTRIBUTES` for clearer grouping. |
| OBI repeatedly reports `422` before discovering a process | Upgrade the receiving self-hosted Logfire deployment. Current managed Logfire accepts OBI v0.13's startup-only metric envelope as an empty success. |
| Requests appear but application logs do not | OBI does not collect application logs. Send them through an OpenTelemetry SDK or the Logfire SDK. |

For deeper traces inside each request, continue with a [Logfire integration](index.md) or configure
an [alternative OpenTelemetry client](../how-to-guides/alternative-clients.md).
