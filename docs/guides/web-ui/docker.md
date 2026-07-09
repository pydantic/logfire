---
title: "Logfire Docker view: CPU, memory, network and block I/O per container"
description: "Browse every Docker container, image and Compose project shipping stats to your Logfire project. Drill into a container's CPU, memory, network and block-I/O charts, alongside the application traces it produced."
---
# Docker

!!! note "Beta — feedback welcome"
    The Docker view is in beta and shipping fixes and improvements quickly. Tell us what's missing or broken in the [Logfire Slack community](https://pydantic.dev/docs/logfire/join-slack/) or email [support@pydantic.dev](mailto:support@pydantic.dev).

The **Docker view** shows every Docker container reporting stats to your project — CPU, memory, network and block I/O — alongside the application traces those containers produced. The same stats are folded three ways: by **container**, by **image**, and by **Compose project**.

You'll find Docker in the project sidebar under **Infrastructure**, after **Kubernetes**.

## What's in the view

Three lenses on the same container stats, all sortable:

- **Containers** — one row per container, with:
    - **Status** — `live` if the container emitted a sample recently, `stale` after a gap, `down` once it's been long enough since the last sample.
    - **Image** it's running.
    - **Host** it runs on — links to the [Hosts view](hosts.md) when that host also reports host metrics.
    - **CPU** utilization (0–100%) with an inline sparkline.
    - **Memory** percent.
    - **Uptime** and **Restarts** (optional columns — see [Setting up](#setting-up)).
- **Images** — containers folded up by image, so you can see how many containers an image is running and their aggregate load.
- **Compose projects** — containers grouped by their Docker Compose project and service.

Summary cards across the top give you the shape at a glance: total containers and their live / stale / down split.

## Container detail page

Click a container to open its detail page, with trend charts for:

- **CPU**
- **Memory** — usage against the container's limit.
- **Network** — split by direction (received vs transmitted), not collapsed into a total.
- **Block I/O** — disk reads vs writes for the container.

## Setting up

Containers populate from the standard OpenTelemetry [`docker_stats` receiver](https://github.com/open-telemetry/opentelemetry-collector-contrib/tree/main/receiver/dockerstatsreceiver). It works on its defaults — no proprietary agent, no per-container config. Add it to the collector you already run for traces, or start a new one:

```yaml
receivers:
  docker_stats:
    collection_interval: 30s
    container_labels_to_metric_labels:   # so the Compose projects tab can group containers
      com.docker.compose.project: compose.project
      com.docker.compose.service: compose.service

processors:
  resourcedetection:
    detectors: [docker]   # names the host from the Docker daemon

exporters:
  otlphttp/logfire:
    endpoint: https://logfire-us.pydantic.dev   # or https://logfire-eu.pydantic.dev
    headers:
      Authorization: ${env:LOGFIRE_TOKEN}

service:
  pipelines:
    metrics:
      receivers: [docker_stats]
      processors: [resourcedetection]
      exporters: [otlphttp/logfire]
```

The receiver reads the local Docker socket (`unix:///var/run/docker.sock` by default) and negotiates the API version automatically; the collector's user just needs permission to read that socket — the `docker` group, or root. The `resourcedetection` processor's `docker` detector reads the host name from that same daemon, so the containers group under their host and link across to the [Hosts view](hosts.md). CPU, memory, network and block-I/O land within a minute or two. For production hardening (memory limiter, batching) see the [OpenTelemetry Collector Overview](../../how-to-guides/otel-collector/otel-collector-overview.md).

The `container_labels_to_metric_labels` mapping is what powers the **Compose projects** tab: `docker_stats` doesn't export container labels on its own, so it lifts Compose's `com.docker.compose.project`/`service` labels into the `compose.project`/`compose.service` attributes the view groups on.

### Optional extras

- **Uptime and Restarts columns** are off by default. Enable them under the receiver:
    ```yaml
    docker_stats:
      metrics:
        container.uptime: {enabled: true}
        container.restarts: {enabled: true}
    ```
- **Running the collector as a container** — use the `-contrib` image (`docker_stats` isn't in the core one), bind-mount the socket in, and run as a user that can read it:
    ```bash
    docker run --rm \
      -v "$(pwd)/collector.yaml:/etc/otelcol-contrib/config.yaml" \
      -v /var/run/docker.sock:/var/run/docker.sock \
      -e LOGFIRE_TOKEN=<your write token from project Settings → Write tokens> \
      --user 0:0 \
      otel/opentelemetry-collector-contrib:latest
    ```
    For a self-hosted or local-dev Logfire on localhost / LAN, reach it over `host.docker.internal` (add `extra_hosts: ["host.docker.internal:host-gateway"]`), since inside the container `localhost` is the collector itself. Mounting the Docker socket gives the collector root-equivalent control of the host, so treat it as a privileged mount.

## Troubleshooting

| Symptom | Likely cause |
|---------|--------------|
| No containers appear | The collector can't read the socket, or nothing is exporting yet. Confirm the socket is readable and add a `debug` exporter to watch metrics in the logs — the `otlphttp` exporter logs only on failure, so "success" is data showing up in Logfire, not a 2xx line. |
| Uptime and Restarts columns are empty | Those two metrics are off by default. Enable `container.uptime` and `container.restarts` under the receiver's `metrics:` block. |
| `api version is too old` at startup | An older collector build isn't auto-negotiating. Pin `api_version: "1.44"` (a quoted string) on the receiver. |
| Containerised collector can't reach a local Logfire | Inside the container `localhost` is the collector itself. For a self-hosted or local-dev Logfire, reach the host via `host.docker.internal` (add `extra_hosts: ["host.docker.internal:host-gateway"]`). A public-cloud Logfire URL needs no change. |
