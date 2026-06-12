---
title: "Logfire Kubernetes view: clusters, namespaces, workloads, pods and nodes"
description: "Browse your Kubernetes clusters, namespaces, workloads, pods, nodes and container images. Sort by restart count, drill from pod to workload to namespace, and jump straight to the traces each pod produced."
---
# Kubernetes

!!! note "Beta — feedback welcome"
    The Kubernetes view is in beta and shipping fixes and improvements quickly. Tell us what's missing or broken in the [Logfire Slack community](https://pydantic.dev/docs/logfire/join-slack/) or email [support@pydantic.dev](mailto:support@pydantic.dev).

The **Kubernetes view** is the cluster-shaped browser for your Kubernetes telemetry. Six lenses on the same data — Clusters, Nodes, Namespaces, Workloads, Pods, and Images — all sortable, with one-click drill-down to the traces each pod produced in the [Live View](live.md).

You'll find Kubernetes in the project sidebar, between **Hosts** and **Metrics**.

![Kubernetes view with the Clusters tab open](../../images/kubernetes/inventory.png)

Switch to the **Pods** tab to drop into individual pod state — restart counts, CPU and memory per pod, status pill, and the workload they belong to:

![Kubernetes Pods tab](../../images/kubernetes/pods-tab.png)

## What's in the view

The top of the page shows summary cards for the whole project: clusters, nodes, namespaces, workloads, pods, and unique container images.

Below the cards, six tabs let you browse by level:

| Tab | Shows |
|-----|-------|
| **Clusters** | One row per cluster, with pod / namespace / node counts and total restarts in the window. |
| **Nodes** | One row per node, with cluster, CPU + sparkline, memory, ready status, and pod count. |
| **Namespaces** | Pod count, CPU and memory usage, restart count. |
| **Workloads** | Workload name and kind, namespace, desired vs ready replicas, CPU, memory, restarts. |
| **Pods** | Status pill (Running / Pending / Failed / Succeeded / Unknown), restart count, CPU, memory, ready state. |
| **Images** | Container image digest, the workloads using it, and total deployed size. |

Restart counts roll up at every level. If a single pod is in a crash loop, you can spot it from the Clusters or Workloads tab without drilling all the way down.

## Drill-down

The view follows the Kubernetes hierarchy you already think in:

- From a **cluster** to the namespaces, nodes and workloads inside it.
- From a **namespace** to the workloads and pods inside it.
- From a **workload** (Deployment, StatefulSet, DaemonSet, etc.) to its pods.
- From a **pod** to its workload, its namespace, its node, **and the traces it produced**.

Every detail page links into the [Live View](live.md) for the trace investigation that ends the question.

## Setting up

The recommended path is the upstream [`opentelemetry-kube-stack`](https://github.com/open-telemetry/opentelemetry-helm-charts/tree/main/charts/opentelemetry-kube-stack) Helm chart. By default it deploys the OpenTelemetry Operator, a DaemonSet `OpenTelemetryCollector` running every preset this view reads from — `kubeletMetrics` (with `metric_groups` already set to `[node, pod, container]`), `clusterMetrics` (`k8s_cluster` with leader election so it only emits from one pod), `hostMetrics`, `kubernetesAttributes` (the trace-enrichment processor), and `kubernetesEvents` — plus the ServiceAccount, RBAC and CRDs it all needs. You just point its OTLP exporter at Logfire:

```yaml
# values.yaml — Logfire-shaped overrides for opentelemetry-kube-stack.
# See the chart's own values.yaml for the full schema; this is only the
# overrides on top of the defaults.

clusterName: my-cluster   # shows up as the row label in the Clusters tab

# Inject the write token into every collector pod the chart deploys.
extraEnvs:
  - name: LOGFIRE_TOKEN
    valueFrom:
      secretKeyRef:
        name: logfire-token
        key: LOGFIRE_TOKEN

# Route the daemon collector's three pipelines to Logfire.
# Override must live under `collectors.daemon.config` — the chart's
# collector-specific config wins over `defaultCRConfig.config`.
collectors:
  daemon:
    config:
      exporters:
        otlphttp/logfire:
          endpoint: https://logfire-us.pydantic.dev   # or https://logfire-eu.pydantic.dev
          headers:
            Authorization: ${env:LOGFIRE_TOKEN}
      service:
        pipelines:
          traces:  {exporters: [otlphttp/logfire]}
          metrics: {exporters: [otlphttp/logfire]}
          logs:    {exporters: [otlphttp/logfire]}
```

```bash
helm repo add open-telemetry https://open-telemetry.github.io/opentelemetry-helm-charts
kubectl create namespace observability
kubectl -n observability create secret generic logfire-token \
  --from-literal=LOGFIRE_TOKEN=<your write token from project Settings → Write tokens>
helm upgrade --install otel-stack open-telemetry/opentelemetry-kube-stack \
  -n observability -f values.yaml
```

Data starts flowing within a minute or two of the daemon pods reaching `Ready`. The chart wires the `k8sattributes` processor into the daemon's trace pipeline so the **drill-down from a pod to the spans that pod emitted** in the [Live View](live.md) works out of the box.

For the full per-piece breakdown (RBAC, both collector configs, the `k8sattributes` processor's pod_association chain, and a kind walkthrough), see the [Kubernetes monitoring](../../how-to-guides/otel-collector/kubernetes-monitoring.md) how-to-guide. For an end-to-end article including a real application sending traces and unified dashboards, see [Full-stack Kubernetes observability with Logfire](https://pydantic.dev/articles/kubernetes-cluster-observability-logfire).

If you have not set anything up yet, the empty state on each tab has a **Set up** button that deep-links to the relevant page of the add-data wizard.
