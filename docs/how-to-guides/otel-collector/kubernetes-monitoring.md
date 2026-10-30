---
title: "Kubernetes monitoring with the OTel Collector"
description: "Ship Kubernetes cluster metrics, node and pod metrics, pod logs, and Kubernetes resource attributes to Logfire via the OpenTelemetry Collector."
---
# Kubernetes monitoring with the OTel Collector

See cluster health, workload state, pod logs, and Kubernetes Events in Logfire without hand-building a monitoring pipeline. This guide uses the upstream OpenTelemetry Kubernetes Helm chart with a balanced configuration that keeps the Kubernetes page working without collecting every signal enabled by the chart.

## What the standard setup collects

The setup on this page collects:

- Kubernetes cluster, workload, node, pod, and container metrics once per minute.
- Pod stdout and stderr, plus Kubernetes Events.
- Kubernetes resource identity for telemetry sent through the Collector.

It does not collect persistent-volume metrics, broad Prometheus scrapes, or host metrics. Those signals are not required by the Kubernetes page and can add substantial volume. You can [collect more Kubernetes data](kubernetes-collect-more.md) after the cluster setup works.

The Collector also accepts application telemetry over the OpenTelemetry Protocol (OTLP), but does not instrument application pods automatically.

## Install with Helm

Use the upstream [`opentelemetry-kube-stack`](https://github.com/open-telemetry/opentelemetry-helm-charts/tree/main/charts/opentelemetry-kube-stack) Helm chart to populate Logfire's [Kubernetes view](../../guides/web-ui/kubernetes.md).

Copy a write token, the credential that lets this deployment send data to your project, from **Project → Settings → Write tokens**.

!!! note "Review volume before installing"
    Infrastructure metrics, pod stdout and stderr, Kubernetes Events, and application telemetry forwarded through the Collector count toward your usage. Volume grows with the number of nodes, pods, and containers. This setup reduces the chart's defaults, but does not guarantee that a cluster fits a particular usage allowance. Review pod logs for sensitive values, use [Collector scrubbing](otel-collector-scrubbing.md) when needed, and [measure projected volume](kubernetes-reduce-volume.md#measure-before-and-after) after installation.

Add the token to a Kubernetes Secret, then provide a small `values.yaml` to name the cluster, select the balanced data set, and route it to Logfire:

```yaml title="values.yaml" collapse="10"
# values.yaml: Logfire-shaped overrides for opentelemetry-kube-stack.
# See the chart's own values.yaml for the full schema; this is only the
# overrides on top of the defaults.

clusterName: my-cluster   # shows up as the row label in the Clusters tab

# Generate the Operator webhook certificate during installation so this works
# on a new cluster without requiring cert-manager first.
opentelemetry-operator:
  admissionWebhooks:
    certManager:
      enabled: false
    autoGenerateCert:
      enabled: true

collectors:
  daemon:
    # Disable the chart's broad cAdvisor and annotated-pod Prometheus scrapes.
    scrape_configs_file: ""
    presets:
      # The Kubernetes page uses kubelet metrics for node resource usage.
      # Enable host metrics separately if you also use the Hosts page.
      hostMetrics:
        enabled: false
    # Scope the write token to the Collector. Top-level `extraEnvs` also
    # copies values into auto-instrumented application pods.
    env:
      - name: LOGFIRE_TOKEN
        valueFrom:
          secretKeyRef:
            name: logfire-token
            key: LOGFIRE_TOKEN
    # Override must live under `collectors.daemon.config`. The chart's
    # collector-specific config wins over `defaultCRConfig.config`.
    config:
      receivers:
        kubelet_stats:
          collection_interval: 60s
          metric_groups: [node, pod, container]
        k8s_cluster:
          collection_interval: 60s
      exporters:
        otlp_http/logfire:
          endpoint: https://logfire-us.pydantic.dev   # or https://logfire-eu.pydantic.dev
          headers:
            Authorization: "Bearer ${env:LOGFIRE_TOKEN}"
      service:
        pipelines:
          traces:  {exporters: [otlp_http/logfire]}
          metrics: {exporters: [otlp_http/logfire]}
          logs:    {exporters: [otlp_http/logfire]}
```

```bash
helm repo add open-telemetry https://open-telemetry.github.io/opentelemetry-helm-charts
kubectl create namespace observability --dry-run=client -o yaml | kubectl apply -f -

printf 'Paste your Logfire write token: '
read -r -s LOGFIRE_TOKEN
printf '\n'
printf '%s' "$LOGFIRE_TOKEN" | kubectl -n observability create secret generic logfire-token \
  --from-file=LOGFIRE_TOKEN=/dev/stdin --dry-run=client -o yaml | kubectl apply -f -
unset LOGFIRE_TOKEN

helm upgrade --install otel-stack open-telemetry/opentelemetry-kube-stack \
  --version 0.20.6 \
  -n observability -f values.yaml
```

Data usually starts flowing within two minutes of the Collector pods reaching `Ready`.

## Verify data arrives

Confirm that the Operator and Collector pods are running:

```bash
kubectl -n observability get opentelemetrycollectors,pods
```

Within two minutes:

1. Open **Kubernetes** in Logfire. You should see your cluster, nodes, namespaces, workloads, and pods.
2. Open **Live** and filter by `k8s.cluster.name`. You should see pod logs and Kubernetes Events.

To inspect the same records from a resource's dedicated **Logs** and **Events** tabs, open the [Kubernetes view](../../guides/web-ui/kubernetes.md#logs-and-events-tabs). The tabs retain your resource scope, time range, and environment.

## Monitor hosts too

The Kubernetes page gets node CPU and memory from kubelet metrics. To populate the separate **Hosts** view with load, disk, filesystem, network, and paging data, set `collectors.daemon.presets.hostMetrics.enabled` to `true` and `collectors.daemon.config.receivers.host_metrics.collection_interval` to `60s` in an additional values file.

??? note "Production considerations"
    - The quickstart generates the Operator webhook certificate so cert-manager is not required. The certificate is valid for 365 days and renewed by `helm upgrade`. If your cluster already uses cert-manager, enable `opentelemetry-operator.admissionWebhooks.certManager` and remove `autoGenerateCert`.
    - The chart disables kubelet certificate verification for compatibility across Kubernetes distributions. When the kubelet certificate chains to your cluster certificate authority, set `collectors.daemon.config.receivers.kubelet_stats.insecure_skip_verify` to `false`. Otherwise, mount its issuer certificate and configure `ca_file`.

## Identify clusters and nodes

Logfire groups Kubernetes data by `k8s.cluster.uid` and `k8s.cluster.name`. The `clusterName` value above stamps `k8s.cluster.name` on every signal. If you run your own Collectors, for example with the upstream [`opentelemetry-collector`](https://github.com/open-telemetry/opentelemetry-helm-charts/tree/main/charts/opentelemetry-collector) chart, you must add a cluster identity yourself.

### Why it matters

The upstream `opentelemetry-collector` chart presets are `kubernetesAttributes`, `kubeletMetrics`, and `clusterMetrics`. With only these presets, only pod and container metrics get `k8s.cluster.uid`. Node metrics get no cluster attribute. Workload and namespace metrics (deployment, daemonset, replicaset, job, and namespace) also get no cluster attribute. Logfire then shows these metrics under **Unknown cluster**, and the cluster's **Nodes** tab is empty.

### Put a cluster identity on every pipeline

Use one of these methods. Use both if you can. The UID is stable, and the name is readable.

- **Set the cluster name.** Add `k8s.cluster.name` to every metric with a `resource` processor. Use the same value in every Collector of that cluster.

    ```yaml
    processors:
      resource/cluster:
        attributes:
          - key: k8s.cluster.name
            value: my-cluster
            action: upsert
    ```

- **Detect the cluster UID.** Turn on the `k8s_api` detector of the [`resourcedetection`](https://github.com/open-telemetry/opentelemetry-collector-contrib/tree/main/processor/resourcedetectionprocessor) processor. Enable only `k8s.cluster.uid`. The detector reads the UID of the `kube-system` namespace, so the Collector's ClusterRole needs `get` on `namespaces`.

    ```yaml
    processors:
      resourcedetection:
        detectors: [k8s_api]
        k8s_api:
          resource_attributes:
            k8s.cluster.uid: {enabled: true}
            k8s.node.name: {enabled: false}
            k8s.node.uid: {enabled: false}
    ```

Add the processor to the metrics pipeline after `k8sattributes`, for example `processors: [k8sattributes, resourcedetection, resource/cluster, batch]`. Do the same in the logs and traces pipelines.

!!! warning "Disable the node attributes of the `k8s_api` detector"
    With its default settings, the `k8s_api` detector writes the Collector's own node into `k8s.node.name` and `k8s.node.uid` on every record. It overwrites the values that are already there. Then all node metrics from the `k8s_cluster` receiver move onto one node, and the other nodes disappear from Logfire. Always set `k8s.node.name` and `k8s.node.uid` to `enabled: false`, as the example above shows.

## Troubleshoot setup

| Symptom | What to check |
|---------|---------------|
| No Collector pods | Run `kubectl -n observability logs deployment/otel-stack-opentelemetry-operator --container manager`. Admission or custom-resource errors appear there. |
| Collector logs show `401` or `403` | Confirm that the endpoint uses the same region as the Logfire project and recreate the Secret with a current write token. |
| Data shows under **Unknown cluster**, or the **Nodes** tab is empty | Make sure every pipeline adds `k8s.cluster.name` or `k8s.cluster.uid`. See [Identify clusters and nodes](#identify-clusters-and-nodes). |
| Collector runs but the Kubernetes page is empty | Run `kubectl -n observability logs -l app.kubernetes.io/name=opentelemetry-collector --tail=200` and look for Kubernetes API or RBAC errors. |
| Application traces do not appear | The standard setup does not modify application pods. Follow [Collect more data from Kubernetes](kubernetes-collect-more.md) to instrument them. |

## Next steps

- [Collect more data](kubernetes-collect-more.md) to instrument applications or enable optional Kubernetes signals.
- [Control monitoring volume](kubernetes-reduce-volume.md) by measuring usage and removing data you do not query.
- [Build a custom Collector deployment](kubernetes-manual-setup.md) when the Helm chart cannot fit your cluster's deployment model.
