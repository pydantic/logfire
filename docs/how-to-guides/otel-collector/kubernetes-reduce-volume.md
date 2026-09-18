---
title: "Reduce Kubernetes monitoring volume"
description: "Reduce Kubernetes metric volume and cost while retaining the data required by Logfire's Kubernetes page."
---
# Reduce Kubernetes monitoring volume

Send fewer Kubernetes metrics, numbers tracked over time such as CPU load, while keeping the current Logfire Kubernetes page working.

Start with the [standard Kubernetes monitoring setup](kubernetes-monitoring.md). It collects the full recommended metric set at the chart's standard intervals. Use the lower-volume configuration only when reducing usage is more important than short-interval, persistent-volume, and Prometheus data.

## Recommended lower-volume configuration

Each receiver is a Collector component that gathers one source of data. These overrides keep the current Logfire Kubernetes page working while reducing receiver frequency, omitting persistent-volume metrics, and disabling the chart's broad Prometheus scrape configuration.

!!! caution "This data is not recoverable"
    After you apply this configuration, Logfire cannot show metric samples that the Collector did not send. Short-lived spikes, persistent-volume metrics, and Prometheus data from kubelet cAdvisor and annotated pods may disappear from queries and alerts. Existing data remains available until its normal retention period ends.

```yaml title="values-low-volume.yaml"
collectors:
  daemon:
    # Disable the chart's broad cAdvisor and annotated-pod Prometheus scrapes.
    scrape_configs_file: ""
    config:
      receivers:
        host_metrics:
          collection_interval: 60s
        kubelet_stats:
          collection_interval: 60s
          metric_groups: [node, pod, container]
          extra_metadata_labels: [container.id]
        k8s_cluster:
          collection_interval: 60s
          node_conditions_to_report: [Ready, MemoryPressure, DiskPressure]
          allocatable_types_to_report: [cpu, memory]
```

Apply the file alongside your normal values:

```bash
helm upgrade --install otel-stack open-telemetry/opentelemetry-kube-stack \
  --version 0.20.6 \
  -n observability \
  -f values.yaml \
  -f values-low-volume.yaml
```

For the from-scratch configuration, apply the same `collection_interval` and `metric_groups` values to the two Collector configs in the [manual setup guide](kubernetes-manual-setup.md).

## What this saves

The Helm chart presets currently collect host and cluster metrics every 10 seconds and kubelet metrics every 15 seconds. Moving them to 60 seconds sends one-sixth and one-quarter as many datapoints respectively. Omitting the `volume` group also avoids a set of metrics for every persistent volume.

The chart's daemon also ships with a Prometheus scrape configuration for kubelet cAdvisor and annotated pods at 30-second intervals. Setting `scrape_configs_file: ""` removes that receiver and its potentially large container and application metric set.

If you later add selected Prometheus targets, wire the named receiver into `service.pipelines.metrics.receivers` without replacing `otlp`, `host_metrics`, `kubelet_stats`, or `k8s_cluster`. A static target on the daemon Collector is scraped once per node and duplicates data. Use node-local discovery that keeps only targets on `${env:OTEL_K8S_NODE_NAME}`, or put cluster-wide static targets on a separate single-replica Collector.

Keep these other volume multipliers off:

- Do not enable `collect_all_network_interfaces`. The default interface is enough for the Kubernetes page.
- Do not enable the per-process `host_metrics` scraper. Process-level metrics multiply with every process on every node.
- Keep cluster-scoped receivers behind leader election or in a single-replica Deployment. Running one on every node duplicates the same cluster data.

## What you give up

- CPU, memory, and health changes are sampled once per minute, so a short-lived spike between samples might not appear.
- Persistent-volume capacity and inode queries or alerts will not work. The current Kubernetes page does not display those metrics.
- Prometheus metrics from kubelet cAdvisor and annotated pods will stop. Application metrics sent over the OpenTelemetry Protocol (OTLP) are unaffected.

Pod logs, Kubernetes Events, and application telemetry sent over OTLP are unchanged. The overlay only changes infrastructure metric receivers and the daemon's Prometheus scrape path.

!!! warning "Check custom queries before reducing volume"
    A metric omitted at the Collector is unavailable to Metrics Explorer, SQL, dashboards, and alerts even when the Kubernetes page does not use it.

## Why the Kubernetes page still works

The lower-volume configuration retains every metric the current page queries:

- Pod state and restarts: `k8s.pod.phase` and `k8s.container.restarts`.
- CPU: `k8s.node.cpu.usage`, `k8s.pod.cpu.usage`, and `container.cpu.usage`.
- Memory: `k8s.node.memory.usage`, `k8s.pod.memory.usage`, and `container.memory.usage`.
- Node health and capacity: `k8s.node.condition_ready`, `k8s.node.condition_memory_pressure`, `k8s.node.condition_disk_pressure`, `k8s.node.allocatable_cpu`, and `k8s.node.allocatable_memory`.
- Workloads: `k8s.deployment.available` and `k8s.deployment.desired`.

Older Collector versions call the three CPU metrics `*.cpu.utilization`. Logfire reads both spellings. Keep the spelling emitted by your Collector version.

Do not remove `k8sattributesprocessor` or its pod, namespace, workload, node, and container identity attributes. Those attributes connect Kubernetes rows to their traces and logs without creating additional metric records.

## Measure before and after

After applying the overlay, wait two minutes and confirm that the Kubernetes page still lists clusters, nodes, workloads, and pods. Then run this in [SQL Workbench](../../guides/web-ui/explore.md) to compare Kubernetes metric volume:

```sql
SELECT
    coalesce(otel_resource_attributes->>'k8s.cluster.name', 'unknown') AS cluster,
    otel_scope_name,
    metric_name,
    count(*) AS metrics_7d
FROM metrics
WHERE recorded_timestamp >= now() - interval '7 days'
  AND otel_resource_attributes->>'k8s.cluster.name' IS NOT NULL
GROUP BY cluster, otel_scope_name, metric_name
ORDER BY metrics_7d DESC;
```

The [Usage Overview dashboard](../../logfire-costs.md#standard-usage-dashboard) also groups metrics by `metric_name`. Use your own result when estimating savings because pod, container, node, and volume counts differ between clusters.

## Troubleshoot the lower-volume setup

| Symptom | What to check |
|---------|---------------|
| The Kubernetes page becomes empty | Confirm that `kubelet_stats` and `k8s_cluster` remain in the metrics pipeline and that the overlay is applied after `values.yaml`. |
| Container CPU or memory is missing | Confirm that `container` remains in `kubelet_stats.metric_groups`. |
| A dashboard or alert loses data | Restore the required metric group, optional metric, or Prometheus target from the standard configuration. Collector-side omissions affect every Logfire query. |

## Next steps

- Return to the [standard configuration](kubernetes-monitoring.md) to restore the full data set.
- [Collect more data](kubernetes-collect-more.md) when a specific diagnostic question is worth the additional usage.
