---
title: "Host Monitoring with the OTel Collector | Logfire"
description: "Ship CPU, memory, disk, filesystem, network, and process metrics from any host to Logfire via the OpenTelemetry Collector hostmetrics receiver."
---
# Host monitoring with the OTel Collector

The OpenTelemetry Collector's [`hostmetrics` receiver](https://github.com/open-telemetry/opentelemetry-collector-contrib/tree/main/receiver/hostmetricsreceiver) reads CPU, memory, disk, filesystem, network, paging and process metrics from the machine the Collector is running on and ships them to Logfire — no SDK required, no application changes. Hosts reporting these metrics show up on the **Hosts** page in Logfire, and the metric series are queryable in **Metrics**, **Explore**, and any dashboard you build on top of them.

This is also the smallest possible working Collector configuration. The same shape works whether the Collector runs as a daemon on a bare VM, a sidecar next to your app, or a DaemonSet in Kubernetes — only the deployment wrapper changes.

## Minimal configuration

```yaml title="otel-collector-config.yaml"
receivers:
  hostmetrics:
    collection_interval: 30s
    scrapers:
      cpu:
        metrics:
          system.cpu.utilization:
            enabled: true
      memory:
        metrics:
          system.memory.utilization:
            enabled: true
      load:
      disk:
      filesystem:
        metrics:
          system.filesystem.utilization:
            enabled: true
      network:
      paging:
      processes:

processors:
  resourcedetection:
    detectors: [env, system]
    system:
      hostname_sources: [os]
  batch:

exporters:
  otlphttp:
    endpoint: "https://logfire-eu.pydantic.info"  # or https://logfire-us.pydantic.info for the US region
    headers:
      Authorization: "Bearer ${env:LOGFIRE_TOKEN}"

service:
  pipelines:
    metrics:
      receivers: [hostmetrics]
      processors: [resourcedetection, batch]
      exporters: [otlphttp]
```

A few things worth calling out:

- **`resourcedetection`** adds the `host.name` (and on cloud VMs, `cloud.provider`, `cloud.region`, etc.) resource attributes to every metric. The Hosts page groups by `host.name`, so a Collector that omits this processor won't appear there.
- **`*.utilization` metrics are off by default in the receiver**, but the Hosts page expects them. Enabling `system.cpu.utilization`, `system.memory.utilization`, and `system.filesystem.utilization` populates the **CPU**, **Memory**, and disk columns directly instead of requiring a downstream rate calculation.
- **Scraper list** is the OTel `hostmetricsreceiver` default set. Drop the ones you don't need to reduce cardinality — `processes` in particular emits a series per running process and can be heavy on busy hosts.
- The endpoint must match the region your project lives in (`logfire-eu` or `logfire-us`). The token is a Logfire write token; pass it via the `LOGFIRE_TOKEN` environment variable on the Collector workload.
- `collection_interval` defaults to `1m` in the receiver. `30s` is a good middle ground; anything faster multiplies series volume — and your bill — without telling you much more about a host.

## Scraper reference

Each entry under `scrapers:` enables one source of host metrics. Pick the ones you need; an empty value (`cpu:`) accepts the receiver defaults.

| Scraper | What it emits | Linux | macOS | Windows |
|---|---|---|---|---|
| `cpu` | Per-core CPU time broken down by state (`user`, `system`, `idle`, `iowait`, ...). | yes | yes | yes |
| `memory` | Used / free / cached / buffered bytes and memory utilization. | yes | yes | yes |
| `load` | 1, 5, and 15 minute system load averages. | yes | yes | yes |
| `disk` | Block-device I/O counters: bytes read/written, operations, weighted I/O time. | yes | yes | yes |
| `filesystem` | Mounted-filesystem usage and inode counts, per device and mountpoint. | yes | yes | yes |
| `network` | Per-interface bytes, packets, errors, dropped packets, and TCP connection counts. | yes | yes | yes |
| `paging` | Swap usage and page-in / page-out counters. | yes | yes | yes |
| `processes` | Aggregate counts of running, blocked, and sleeping processes on the host. | yes | yes | no |
| `process` | **Per-process** CPU, memory, and disk I/O for every running PID. | yes | yes | yes |

!!! note
    On macOS and Windows the `processes` (aggregate counts) and `process` (per-PID) scrapers behave differently from Linux — `processes` is unavailable on Windows, and several per-process attributes only populate on Linux. If you're standardizing on a single config across operating systems, lean on `cpu`, `memory`, `load`, `disk`, `filesystem`, `network`, and `paging` and add the process scrapers only where they're supported.

For the exhaustive list of metric names and attributes each scraper emits, see the [`hostmetricsreceiver` documentation](https://github.com/open-telemetry/opentelemetry-collector-contrib/blob/main/receiver/hostmetricsreceiver/documentation.md).

## Cardinality and cost

The `processes` and `process` scrapers are the two you have to think about.

- `processes` emits a handful of aggregate counts per host. It's cheap.
- `process` emits **one set of series per process PID** — every short-lived `ps`, every Node worker, every `kubectl exec`. On a busy host or build agent this can mean tens of thousands of active series before lunch, and each new PID is a fresh series even if the binary is identical.

If you turn on `process`, scope it. The receiver supports `include` and `exclude` filters on process name, and you almost always want one or the other:

```yaml title="otel-collector-config.yaml"
receivers:
  hostmetrics:
    collection_interval: 30s
    scrapers:
      process:
        mute_process_name_error: true
        include:
          names: [postgres, redis-server, nginx, node, python]
          match_type: strict
```

Or, equivalently, exclude the noisy ones:

```yaml
      process:
        mute_process_name_error: true
        exclude:
          names: [".*\\.tmp", "sshd", "bash", "sh"]
          match_type: regexp
```

`mute_process_name_error: true` silences the warnings the receiver logs when it can't read `/proc/<pid>/comm` for a process that exited between scrape ticks — common, noisy, and not actionable.

!!! tip
    If you only need a "what's running on this host" view, leave `process` off entirely and rely on `processes` plus `cpu` / `memory`. Per-process metrics are most useful when you have a small, stable set of long-running services you want to chart individually.

## Cloud provider detection

The `resourcedetection` processor attaches `cloud.provider`, `cloud.region`, `host.id`, and friends to every metric so cloud VMs land on the Hosts page with the right metadata and so dashboards can slice by region. Enable the detectors that match where the Collector might run:

```yaml title="otel-collector-config.yaml"
processors:
  resourcedetection:
    detectors: [env, system, ec2, gcp, azure]
    timeout: 5s
    override: false
    system:
      hostname_sources: [os]
```

A few details:

- Order matters. Detectors run left-to-right, and with `override: false` the first detector to set an attribute wins. Put `env` first so anything you've baked into `OTEL_RESOURCE_ATTRIBUTES` (a deployment name, a cluster tag) takes precedence over auto-detected values.
- `ec2`, `gcp`, and `azure` each hit the cloud provider's instance metadata service. They cost nothing on the wrong cloud — the detector times out and moves on — so it's safe to list all three on a config that might be deployed anywhere.
- For Kubernetes, add the matching managed-cluster detector (`eks`, `gke`, or `aks`) to pick up `k8s.cluster.name`. See the [resourcedetection processor README](https://github.com/open-telemetry/opentelemetry-collector-contrib/tree/main/processor/resourcedetectionprocessor) for the full list.

!!! warning
    Without `resourcedetection` (or some other source of `host.name`), the Collector's metrics still flow into Logfire but the host will not appear on the **Hosts** page — that page groups by `host.name`, and there's nothing for it to group by.

## Running as a Kubernetes DaemonSet

In Kubernetes you want one Collector per node, scraping that node's host metrics. That means a DaemonSet — and a few specific bits of pod spec so the receiver reads the **node's** CPU, memory, network, and process tables instead of the container's namespaced view.

Three things have to be right:

1. `hostNetwork: true` and `hostPID: true` on the pod, so the network and process scrapers see the node.
2. Mount the host's `/proc` and `/sys` into the container (read-only is fine).
3. Set `root_path: /host` on the `hostmetrics` receiver so it reads from those mounts instead of the container root.

```yaml title="otel-collector-config.yaml"
receivers:
  hostmetrics:
    collection_interval: 30s
    root_path: /host
    scrapers:
      cpu:
      memory:
      load:
      disk:
      filesystem:
      network:
      paging:
      processes:

processors:
  resourcedetection:
    detectors: [env, system, ec2, gcp, azure]
    timeout: 5s
    override: false
  batch:

exporters:
  otlphttp:
    endpoint: "https://logfire-eu.pydantic.info"
    headers:
      Authorization: "Bearer ${env:LOGFIRE_TOKEN}"

service:
  pipelines:
    metrics:
      receivers: [hostmetrics]
      processors: [resourcedetection, batch]
      exporters: [otlphttp]
```

And the DaemonSet that runs it:

```yaml title="otel-collector-daemonset.yaml"
apiVersion: apps/v1
kind: DaemonSet
metadata:
  name: otel-collector-hostmetrics
  namespace: observability
spec:
  selector:
    matchLabels:
      app: otel-collector-hostmetrics
  template:
    metadata:
      labels:
        app: otel-collector-hostmetrics
    spec:
      hostNetwork: true
      hostPID: true
      dnsPolicy: ClusterFirstWithHostNet
      containers:
        - name: otel-collector
          image: otel/opentelemetry-collector-contrib:latest
          args: ["--config=/etc/otel/config.yaml"]
          env:
            - name: LOGFIRE_TOKEN
              valueFrom:
                secretKeyRef:
                  name: logfire
                  key: write-token
            - name: K8S_NODE_NAME
              valueFrom:
                fieldRef:
                  fieldPath: spec.nodeName
          volumeMounts:
            - name: config
              mountPath: /etc/otel
            - name: hostfs-proc
              mountPath: /host/proc
              readOnly: true
            - name: hostfs-sys
              mountPath: /host/sys
              readOnly: true
            - name: hostfs-root
              mountPath: /host/root
              readOnly: true
              mountPropagation: HostToContainer
      volumes:
        - name: config
          configMap:
            name: otel-collector-hostmetrics
        - name: hostfs-proc
          hostPath:
            path: /proc
        - name: hostfs-sys
          hostPath:
            path: /sys
        - name: hostfs-root
          hostPath:
            path: /
```

A couple of things to be deliberate about:

- `hostNetwork: true` puts the Collector on the node's network namespace, which is what makes the `network` scraper return real interface stats and lets `resourcedetection`'s cloud detectors reach the instance metadata service. It also means the Collector's ports are exposed on the node, so don't bind anything you don't intend to.
- `hostPID: true` is what lets the `processes` / `process` scrapers see PIDs other than the Collector's own.
- The `filesystem` scraper needs the host root mounted (commonly at `/host/root` with `mountPropagation: HostToContainer`) to report node disk usage rather than the container's overlay. If you only care about CPU/memory/network, you can omit that mount and drop `filesystem` from the scraper list.

## Running on a bare host

Outside of Kubernetes, no special configuration is required — the Collector already has the host's `/proc` and `/sys`. Drop the config in place and run:

```bash
LOGFIRE_TOKEN=<your-write-token> \
  otelcol-contrib --config otel-collector-config.yaml
```

For long-running deployments, wrap that in a systemd unit (or your init system of choice) and put `LOGFIRE_TOKEN` in an `EnvironmentFile=` it reads at startup rather than baking the token into the unit.

## You should see this machine on the Hosts page

Within a minute or two of the Collector starting, the host shows up on the **Hosts** page keyed by `host.name`. From there:

- Click the host to drill into per-host CPU, memory, disk, and network charts.
- Open **Explore** to query the raw metric series — useful for ad-hoc questions like "show me every host where filesystem utilization is above 90%".
- Build a dashboard on top of the metrics if you want a persistent view.

If a host doesn't appear, the cause is almost always one of: missing `resourcedetection` (no `host.name`), wrong region in the `otlphttp` endpoint, or — in Kubernetes — a missing `root_path: /host` or one of the `hostPath` mounts, so the receiver is happily scraping the container's view instead of the node's.
