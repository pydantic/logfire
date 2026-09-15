---
title: "Collect more data from Kubernetes"
description: "Extend Logfire Kubernetes monitoring with application traces, optional diagnostic and network metrics, and additional Kubernetes objects."
---
# Collect more data from Kubernetes

Add application traces, automatic runtime instrumentation, failure reasons, service endpoint health, per-interface network metrics, or extra Kubernetes object state after standard cluster monitoring works.

A trace is the full journey of one request, made of nested spans. A span is one operation with a name, a start, and a duration. Complete the [standard Kubernetes monitoring setup](kubernetes-monitoring.md) first; it gives Logfire the cluster, node, pod, container, host, log, and event data required by the Kubernetes page.

OpenTelemetry Protocol (OTLP) is the standard wire format Logfire uses to receive telemetry.

## What the standard setup already collects

| Data | Standard setup |
|------|----------------|
| Cluster, workload, node, pod, container, and volume metrics | Yes |
| Host CPU, memory, disk, filesystem, network, and paging metrics | Yes |
| Kubelet cAdvisor and annotated-pod Prometheus metrics | Yes, through the daemon's default scrape configuration |
| Pod stdout and stderr | Yes, through the chart's `logsCollection` preset |
| Kubernetes Events | Yes, through the `kubernetesEvents` preset |
| Kubernetes identity on telemetry | Yes, through `k8sattributesprocessor` |
| Application traces | Only when the application already sends OTLP |
| Automatic application instrumentation | No |

The chart installs the OpenTelemetry Operator, but its `Instrumentation` resource is disabled by default. Installing the chart alone does not modify your application pods.

!!! caution "This sends more data"
    Each option on this page sends additional telemetry to Logfire, where it is stored and counts toward your usage. Kubernetes object records may include workload configuration. Enable only the signals you intend to query, and review the data before sending it from the cluster.

## Trace application workloads automatically

For Python and TypeScript applications, the native [Logfire instrumentation guides](../../instrument/index.md) provide the richest framework and AI visibility. Use Operator injection when changing the application image or startup command is impractical.

Enable the chart's `Instrumentation` resource and point it at the daemon Collector service. The names below assume the Helm release is `otel-stack` in the `observability` namespace; replace both parts if yours differ.

Keep `LOGFIRE_TOKEN` under `collectors.daemon.env` as shown in the standard setup. Do not move it to the chart's top-level `extraEnvs`: the chart also copies those values into auto-instrumented application pods.

```yaml title="values-instrumentation.yaml"
instrumentation:
  enabled: true
  exporter:
    endpoint: http://otel-stack-daemon-collector.observability.svc:4317
  python:
    env:
      # Python auto-instrumentation exports OTLP/HTTP by default.
      - name: OTEL_EXPORTER_OTLP_ENDPOINT
        value: http://otel-stack-daemon-collector.observability.svc:4318
  dotnet:
    env:
      - name: OTEL_EXPORTER_OTLP_ENDPOINT
        value: http://otel-stack-daemon-collector.observability.svc:4318
```

Apply the additional values and restart the workloads you want to instrument:

```bash
helm upgrade --install otel-stack open-telemetry/opentelemetry-kube-stack \
  --version 0.20.6 \
  -n observability \
  -f values.yaml \
  -f values-instrumentation.yaml
```

Add one language-specific annotation to the pod template, not the top-level Deployment metadata:

| Runtime | Pod-template annotation |
|---------|-------------------------|
| Python | `instrumentation.opentelemetry.io/inject-python: "observability/otel-stack"` |
| Node.js | `instrumentation.opentelemetry.io/inject-nodejs: "observability/otel-stack"` |
| Java | `instrumentation.opentelemetry.io/inject-java: "observability/otel-stack"` |
| .NET | `instrumentation.opentelemetry.io/inject-dotnet: "observability/otel-stack"` |

The namespace-qualified value is important when your application runs outside `observability`. If the `Instrumentation` resource and application share a namespace, you can use `"true"` instead.

Go injection is also available, but it uses an extended Berkeley Packet Filter (eBPF) sidecar with additional privileges and operator configuration. Follow the upstream guide rather than enabling it as a routine default.

For example:

```yaml title="deployment.yaml"
apiVersion: apps/v1
kind: Deployment
metadata:
  name: checkout
spec:
  selector:
    matchLabels:
      app: checkout
  template:
    metadata:
      labels:
        app: checkout
      annotations:
        instrumentation.opentelemetry.io/inject-python: "observability/otel-stack"
    spec:
      containers:
        - name: checkout
          image: example/checkout:latest
```

The Operator injects instrumentation when it creates a new pod. Restart an existing Deployment after adding the annotation:

```bash
kubectl -n <application-namespace> rollout restart deployment/checkout
```

See the upstream [OpenTelemetry Operator auto-instrumentation guide](https://github.com/open-telemetry/opentelemetry-operator/tree/main/docs/auto-instrumentation) for supported runtimes, multi-container selection, security requirements, and language-specific limitations.

## Collect every network interface

By default, `kubeletstatsreceiver` reports pod and node network metrics for the primary interface. Enable all interfaces only when per-interface traffic and error analysis is worth the additional series:

```yaml
collectors:
  daemon:
    config:
      receivers:
        kubelet_stats:
          collect_all_network_interfaces:
            pod: true
            node: true
```

Each interface adds another set of network metrics for every affected pod or node. Check the [lower-volume guide](kubernetes-reduce-volume.md) before enabling this on a large cluster.

## Enable optional diagnostic metrics

The receivers have additional development-stage metrics that the chart leaves disabled. Enable only the questions you intend to answer. For example, this adds container utilization against configured limits, ephemeral-storage usage, pod failure reasons, and service endpoint health:

```yaml title="values-diagnostic-metrics.yaml"
collectors:
  daemon:
    config:
      receivers:
        kubelet_stats:
          metrics:
            k8s.container.cpu_limit_utilization: {enabled: true}
            k8s.container.memory_limit_utilization: {enabled: true}
            k8s.container.ephemeral_storage.usage: {enabled: true}
        k8s_cluster:
          metrics:
            k8s.pod.status_reason: {enabled: true}
            k8s.service.endpoint.count: {enabled: true}
```

These metrics are not required by Logfire's Kubernetes page and may change with Collector releases. Check their names and stability in the current [`kubeletstatsreceiver`](https://github.com/open-telemetry/opentelemetry-collector-contrib/blob/main/receiver/kubeletstatsreceiver/documentation.md) and [`k8sclusterreceiver`](https://github.com/open-telemetry/opentelemetry-collector-contrib/blob/main/receiver/k8sclusterreceiver/documentation.md) documentation before depending on them in alerts.

## Collect additional Kubernetes objects

The standard setup streams Kubernetes Events and converts cluster state into metrics. The chart can also export Kubernetes resources themselves as log records, including workloads, role-based access control (RBAC) configuration, storage, networking, autoscaling, policies, and custom resource definitions.

Enable only the object groups you intend to query. Object snapshots can be large, may contain configuration you do not want to send to a third party, and are not required by the Kubernetes page. Review the chart's [`kubernetesObjects` preset](https://github.com/open-telemetry/opentelemetry-helm-charts/blob/main/charts/opentelemetry-kube-stack/values.yaml) and the upstream [`k8sobjectsreceiver`](https://github.com/open-telemetry/opentelemetry-collector-contrib/tree/main/receiver/k8sobjectsreceiver) before enabling it.

## Add application and Prometheus metrics

The chart's daemon scrape configuration collects pods with Prometheus-style annotations. For an application endpoint, add `prometheus.io/scrape: "true"`, its port, and its path to the pod template. Avoid scraping the same endpoint from another Prometheus or Collector path unless duplicate metrics are intentional.

You can also send application metrics over the daemon Collector's existing OTLP receiver. Metrics, traces, and logs sent that way receive the same Kubernetes resource attributes before they reach Logfire.

## Confirm the additional data

- Open **Live** and filter by `k8s.namespace.name`, `k8s.deployment.name`, or `k8s.pod.name` to find application traces and pod logs.
- Open **Metrics Explorer** and search for the new metric names before building dashboards or alerts.
- Check the Collector and Operator logs when injection or collection does not appear:

    ```bash
    kubectl -n observability logs deployment/otel-stack-opentelemetry-operator --container manager
    kubectl -n observability logs -l app.kubernetes.io/name=opentelemetry-collector
    ```

## Troubleshoot additional collection

| Symptom | What to check |
|---------|---------------|
| An annotated workload has no traces | Confirm that the annotation names `observability/otel-stack`, then restart the workload so the Operator can modify new pods. |
| Python or .NET pods start but send no data | Confirm that the HTTP endpoint uses port `4318`; Java and Node.js use the shared gRPC endpoint on `4317`. |
| Optional metrics do not appear | Check the Collector version against the linked receiver documentation. Development-stage metric names can change between releases. |
| Collector memory or usage grows unexpectedly | Disable the latest option you enabled, then compare volume by `otel_scope_name` and `metric_name` in Metrics Explorer. |

## Next steps

- Return to the [standard setup](kubernetes-monitoring.md) to verify the required Kubernetes data first.
- Use the [lower-volume configuration](kubernetes-reduce-volume.md) when the additional signals cost more than the questions they answer.
