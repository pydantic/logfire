---
title: "Kubernetes monitoring with the OTel Collector"
description: "Ship Kubernetes cluster metrics, node and pod metrics, pod logs, and Kubernetes resource attributes to Logfire via the OpenTelemetry Collector."
---
# Kubernetes monitoring with the OTel Collector

See cluster health, workload state, pod logs, and Kubernetes Events in Logfire without hand-building a monitoring pipeline. This guide uses the upstream OpenTelemetry Kubernetes Helm chart; most teams only need the setup on this page.

## What the standard setup collects

The default setup collects:

- Kubernetes cluster, workload, node, pod, container, and persistent-volume metrics.
- Host CPU, memory, disk, filesystem, network, and paging metrics.
- Kubelet cAdvisor and annotated-pod Prometheus metrics.
- Pod stdout and stderr, plus Kubernetes Events.
- Kubernetes resource identity for telemetry sent through the Collector.

It also accepts application telemetry over OTLP, but does not instrument application pods automatically. Add that after the cluster setup is working.

## Install with Helm

Use the upstream [`opentelemetry-kube-stack`](https://github.com/open-telemetry/opentelemetry-helm-charts/tree/main/charts/opentelemetry-kube-stack) Helm chart to populate Logfire's [Kubernetes view](../../guides/web-ui/kubernetes.md).

Copy a write token, the credential that lets this deployment send data to your project, from **Project → Settings → Write tokens**.

!!! note "What this sends"
    Infrastructure metrics, pod stdout and stderr, Kubernetes Events, and application telemetry forwarded through the Collector count toward your usage. Review pod logs for sensitive values and use [Collector scrubbing](otel-collector-scrubbing.md) when needed.

Add the token to a Kubernetes Secret, then provide a small `values.yaml` to name the cluster and route the chart's default data set to Logfire:

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
2. Open **Hosts**. You should see one host for each node reporting host metrics.
3. Open **Live** and filter by `k8s.cluster.name`. You should see pod logs and Kubernetes Events.

??? note "Production considerations"
    - The quickstart generates the Operator webhook certificate so cert-manager is not required. The certificate is valid for 365 days and renewed by `helm upgrade`. If your cluster already uses cert-manager, enable `opentelemetry-operator.admissionWebhooks.certManager` and remove `autoGenerateCert`.
    - The chart disables kubelet certificate verification for compatibility across Kubernetes distributions. When the kubelet certificate chains to your cluster certificate authority, set `collectors.daemon.config.receivers.kubelet_stats.insecure_skip_verify` to `false`. Otherwise, mount its issuer certificate and configure `ca_file`.

## Troubleshoot setup

| Symptom | What to check |
|---------|---------------|
| No Collector pods | Run `kubectl -n observability logs deployment/otel-stack-opentelemetry-operator --container manager`. Admission or custom-resource errors appear there. |
| Collector logs show `401` or `403` | Confirm that the endpoint uses the same region as the Logfire project and recreate the Secret with a current write token. |
| Collector runs but the Kubernetes page is empty | Run `kubectl -n observability logs -l app.kubernetes.io/name=opentelemetry-collector --tail=200` and look for Kubernetes API or RBAC errors. |
| Application traces do not appear | The standard setup does not modify application pods. Follow [Collect more data from Kubernetes](kubernetes-collect-more.md) to instrument them. |

## Next steps

- [Collect more data](kubernetes-collect-more.md) to instrument applications or enable optional Kubernetes signals.
- [Reduce data volume](kubernetes-reduce-volume.md) to trade collection detail for lower usage.
- [Build a custom Collector deployment](kubernetes-manual-setup.md) when the Helm chart cannot fit your cluster's deployment model.
