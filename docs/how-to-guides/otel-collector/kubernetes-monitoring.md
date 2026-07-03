---
title: "Kubernetes Monitoring with the OTel Collector | Logfire"
description: "Ship Kubernetes cluster metrics, node and pod metrics, pod logs, and Kubernetes resource attributes to Logfire via the OpenTelemetry Collector."
---
# Kubernetes monitoring with the OTel Collector

This page is the end-to-end guide for monitoring a Kubernetes cluster with the OpenTelemetry Collector and Logfire — cluster-level state and events, per-node container CPU/memory/network/disk, pod stdout/stderr logs, and the Kubernetes resource attributes (`k8s.cluster.name`, `k8s.node.name`, `k8s.namespace.name`, `k8s.pod.name`, …) that make all of the above queryable and groupable in the Logfire UI.

If you only want one slice of this, jump straight to the relevant section. Every snippet below is a working example you can `kubectl apply -f` against a real cluster (managed or local — kind, minikube, k3s, Docker Desktop).

## Quickstart: the `opentelemetry-kube-stack` Helm chart

For the fastest path from an empty cluster to a populated [Kubernetes view](../../guides/web-ui/kubernetes.md), use the upstream [`opentelemetry-kube-stack`](https://github.com/open-telemetry/opentelemetry-helm-charts/tree/main/charts/opentelemetry-kube-stack) Helm chart. By default it deploys the OpenTelemetry Operator and a DaemonSet `OpenTelemetryCollector` running every preset the view reads from — `kubeletMetrics` (with `metric_groups: [node, pod, container]`), `clusterMetrics` (`k8s_cluster` with `k8s_leader_elector` so it only emits from one pod), `hostMetrics`, `kubernetesAttributes`, `kubernetesEvents` — plus the ServiceAccount, CRDs and RBAC it all needs. You provide a small `values.yaml` to point its OTLP exporter at Logfire:

```yaml
# values.yaml — Logfire-shaped overrides for opentelemetry-kube-stack.
# See the chart's own values.yaml for the full schema; this is only the
# overrides on top of the defaults.

clusterName: my-cluster   # shows up as the row label in the Clusters tab

extraEnvs:
  - name: LOGFIRE_TOKEN
    valueFrom:
      secretKeyRef:
        name: logfire-token
        key: LOGFIRE_TOKEN

# Override must live under `collectors.daemon.config` — the chart's
# collector-specific config wins over `defaultCRConfig.config`.
collectors:
  daemon:
    config:
      exporters:
        otlphttp/logfire:
          endpoint: https://logfire-us.pydantic.dev   # or https://logfire-eu.pydantic.dev
          headers:
            Authorization: "Bearer ${env:LOGFIRE_TOKEN}"
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

Data starts flowing within a minute or two of the daemon pods reaching `Ready`. Validated against a 3-node kind cluster with chart 0.15.2 / operator + collector 0.151.0; the daemon collector exports cleanly with no dropped batches, and the `k8s_cluster` receiver completes initial cache sync via leader election.

The rest of this page is the **from-scratch walkthrough** — recommended if you want to understand every piece, customise beyond what the chart's value overrides expose, or deploy without the chart's bundled Operator (for example on a managed platform that already provides one). If you took the Helm path above, you can skip directly to [What `k8sattributesprocessor` actually does](#what-k8sattributesprocessor-actually-does) and [Verifying it works on the Logfire side](#verifying-it-works-on-the-logfire-side).

## The two-Collector pattern

A single Collector workload cannot collect everything in Kubernetes cleanly. Some receivers describe the cluster as a whole, and some describe a node from the inside. Mixing the two in one deployment either duplicates data N times across N nodes or misses node-local data entirely.

The recommended layout is two Collector workloads sharing one image, one config schema, and one ServiceAccount:

- **Cluster-scoped Collector** — a `Deployment` with **exactly one replica**. Runs:
    - [`k8sclusterreceiver`](https://github.com/open-telemetry/opentelemetry-collector-contrib/tree/main/receiver/k8sclusterreceiver) — node count, pod phases, deployment/daemonset replica status, allocatable resources. Talks to the API server, not the nodes. Running this on every node would multiply every metric by N.
    - [`k8sobjectsreceiver`](https://github.com/open-telemetry/opentelemetry-collector-contrib/tree/main/receiver/k8sobjectsreceiver) — Kubernetes Events (pod scheduling, OOMKills, image pull failures, etc.) as log records. The upstream README is explicit: "This receiver must be deployed as one replica, otherwise it'll be producing duplicated data."
    - [`k8sattributesprocessor`](https://github.com/open-telemetry/opentelemetry-collector-contrib/tree/main/processor/k8sattributesprocessor) — to enrich the cluster-scoped data with namespace/workload attributes before exporting.

- **Per-node Collector** — a `DaemonSet`, one Pod per node. Runs:
    - [`kubeletstatsreceiver`](https://github.com/open-telemetry/opentelemetry-collector-contrib/tree/main/receiver/kubeletstatsreceiver) — talks to the local node's kubelet on `https://<node>:10250/stats/summary` and emits container/pod/node CPU, memory, network, filesystem, volume metrics. Must run on every node; can only see its own node.
    - [`filelog`](https://github.com/open-telemetry/opentelemetry-collector-contrib/tree/main/receiver/filelogreceiver) — tails `/var/log/pods/*/*/*.log` to ship pod stdout/stderr. Only readable from a host-mounted volume on the node itself.
    - Optionally [`hostmetrics`](https://github.com/open-telemetry/opentelemetry-collector-contrib/tree/main/receiver/hostmetricsreceiver) with `root_path: /host` — node-level CPU, load, paging, processes from `/proc` and `/sys`.
    - An `otlp` receiver — to enrich and forward traces/logs/metrics from your apps running on the same node.
    - `k8sattributesprocessor` with `filter.node_from_env_var: KUBE_NODE_NAME` — to enrich everything with pod/workload metadata while only watching pods on the local node.

!!! tip "Mental model"
    *"Things about the cluster"* → one Deployment.
    *"Things about a node, or things sent by Pods on a node"* → DaemonSet.

The two share one ClusterRole and one ServiceAccount because the receivers and processor want the same set of read permissions on the Kubernetes API.

## Prerequisites: write token and namespace

We'll deploy everything into a dedicated `observability` namespace and read the Logfire write token from a Secret.

```shell
kubectl create namespace observability
```

Create a Logfire write token (see [Create Write Tokens](../create-write-tokens.md)) and store it as a Secret:

```shell
kubectl -n observability create secret generic logfire-token \
  --from-literal=logfire-token=your-write-token
```

In production prefer a real secrets manager — for example [External Secrets Operator](https://external-secrets.io/latest/) syncing from AWS Secrets Manager, GCP Secret Manager, or Vault.

## RBAC: one ClusterRole for both Collectors

Both the Deployment and the DaemonSet authenticate as the same `otel-collector` ServiceAccount. The ClusterRole below is the union of what all four components (`k8sclusterreceiver`, `k8sobjectsreceiver`, `kubeletstatsreceiver`, `k8sattributesprocessor`) need. It's all read-only — `get`, `list`, `watch`.

```yaml title="rbac.yaml"
apiVersion: v1
kind: ServiceAccount
metadata:
  name: otel-collector
  namespace: observability
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: otel-collector
rules:
  # Core resources — used by all four components.
  - apiGroups: [""]
    resources:
      - events
      - namespaces
      - namespaces/status
      - nodes
      - nodes/spec
      - nodes/stats        # kubeletstatsreceiver: GET /stats/summary
      - nodes/proxy        # kubeletstatsreceiver: when the API server proxies the kubelet
      - persistentvolumeclaims
      - persistentvolumes
      - pods
      - pods/status
      - replicationcontrollers
      - replicationcontrollers/status
      - resourcequotas
      - services
    verbs: ["get", "list", "watch"]
  - apiGroups: ["apps"]
    resources:
      - daemonsets
      - deployments
      - replicasets
      - statefulsets
    verbs: ["get", "list", "watch"]
  - apiGroups: ["extensions"]
    resources:
      - daemonsets
      - deployments
      - replicasets
    verbs: ["get", "list", "watch"]
  - apiGroups: ["batch"]
    resources:
      - jobs
      - cronjobs
    verbs: ["get", "list", "watch"]
  - apiGroups: ["autoscaling"]
    resources:
      - horizontalpodautoscalers
    verbs: ["get", "list", "watch"]
  - apiGroups: ["events.k8s.io"]
    resources:
      - events
    verbs: ["get", "list", "watch"]
  - apiGroups: ["discovery.k8s.io"]
    resources:
      - endpointslices
    verbs: ["get", "list", "watch"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: otel-collector
subjects:
  - kind: ServiceAccount
    name: otel-collector
    namespace: observability
roleRef:
  kind: ClusterRole
  name: otel-collector
  apiGroup: rbac.authorization.k8s.io
```

```shell
kubectl apply -f rbac.yaml
```

!!! note "Why so many resources?"
    `k8sclusterreceiver` walks the whole workload graph to compute things like "how many replicas does this Deployment want vs. have right now?" and "is this DaemonSet rolled out?". It needs read access to every workload kind. `kubeletstatsreceiver` needs `nodes/stats` for the actual metric scrape. `k8sattributesprocessor` needs `pods` + `namespaces` (+ `replicasets` to resolve `k8s.deployment.name` from a pod's owner chain).

If you want to limit a single Collector to one namespace, swap the `ClusterRole` for a `Role` and the `ClusterRoleBinding` for a `RoleBinding`. You lose `k8s.cluster.uid` and any cross-namespace workload roll-ups.

## Cluster-scoped Collector (Deployment)

This is the single-replica Collector that talks to the API server and ships cluster state plus Kubernetes Events.

### Config

```yaml title="cluster-collector-config.yaml"
apiVersion: v1
kind: ConfigMap
metadata:
  name: otel-cluster-collector-config
  namespace: observability
data:
  config.yaml: |-
    receivers:
      # Cluster-level metrics: pod phase, deployment available/desired replicas,
      # node conditions, allocatable cpu/memory, etc.
      k8s_cluster:
        collection_interval: 30s
        node_conditions_to_report: [Ready, MemoryPressure, DiskPressure, PIDPressure]
        allocatable_types_to_report: [cpu, memory, ephemeral-storage, pods]

      # Kubernetes Events as OTel log records.
      # Watch mode keeps a long-lived connection open; pull mode polls.
      k8sobjects:
        auth_type: serviceAccount
        objects:
          - name: events
            mode: watch
            group: events.k8s.io

    processors:
      # Enrich namespace-scoped metrics with workload metadata.
      # This Collector is a Deployment, not a DaemonSet, so we do NOT filter by node.
      k8sattributes:
        auth_type: serviceAccount
        passthrough: false
        extract:
          metadata:
            - k8s.cluster.uid
            - k8s.namespace.name
            - k8s.deployment.name
            - k8s.statefulset.name
            - k8s.daemonset.name
            - k8s.cronjob.name
            - k8s.job.name
            - k8s.node.name
        pod_association:
          - sources:
              - from: resource_attribute
                name: k8s.pod.uid
          - sources:
              - from: resource_attribute
                name: k8s.pod.ip

      batch:
        send_batch_size: 1000
        timeout: 5s

    exporters:
      otlphttp:
        # US:  https://logfire-us.pydantic.dev
        # EU:  https://logfire-eu.pydantic.dev
        endpoint: "https://logfire-eu.pydantic.dev"
        headers:
          Authorization: "Bearer ${env:LOGFIRE_TOKEN}"

    service:
      pipelines:
        metrics:
          receivers: [k8s_cluster]
          processors: [k8sattributes, batch]
          exporters: [otlphttp]
        logs:
          receivers: [k8s_cluster, k8sobjects]
          processors: [k8sattributes, batch]
          exporters: [otlphttp]
```

### Deployment

```yaml title="cluster-collector.yaml"
apiVersion: apps/v1
kind: Deployment
metadata:
  name: otel-cluster-collector
  namespace: observability
  labels:
    app: otel-collector
    component: cluster
spec:
  # MUST be 1. k8sclusterreceiver and k8sobjectsreceiver both produce duplicate
  # data if more than one replica is running.
  replicas: 1
  strategy:
    type: Recreate
  selector:
    matchLabels:
      app: otel-collector
      component: cluster
  template:
    metadata:
      labels:
        app: otel-collector
        component: cluster
    spec:
      serviceAccountName: otel-collector
      containers:
        - name: otel-collector
          image: otel/opentelemetry-collector-contrib:0.128.0
          args: ["--config=/etc/otelcol-contrib/config.yaml"]
          env:
            - name: LOGFIRE_TOKEN
              valueFrom:
                secretKeyRef:
                  name: logfire-token
                  key: logfire-token
          resources:
            requests:
              cpu: 100m
              memory: 256Mi
            limits:
              cpu: 500m
              memory: 512Mi
          volumeMounts:
            - mountPath: /etc/otelcol-contrib/config.yaml
              name: config
              subPath: config.yaml
              readOnly: true
      volumes:
        - name: config
          configMap:
            name: otel-cluster-collector-config
```

```shell
kubectl apply -f cluster-collector-config.yaml
kubectl apply -f cluster-collector.yaml
```

!!! warning "Run exactly one replica"
    `replicas: 1` plus `strategy: Recreate` is intentional. A rolling update would briefly run two replicas of `k8sobjectsreceiver`, which would double-emit every Kubernetes Event for the overlap window. If you need high availability, use the [`k8s_leader_elector` extension](https://github.com/open-telemetry/opentelemetry-collector-contrib/tree/main/extension/k8sleaderelector) to keep one active at a time.

## Per-node Collector (DaemonSet)

This Collector runs once per node and is the workhorse: kubelet metrics, pod logs, optional host metrics, and OTLP ingest for apps on the node.

### Config

```yaml title="node-collector-config.yaml"
apiVersion: v1
kind: ConfigMap
metadata:
  name: otel-node-collector-config
  namespace: observability
data:
  config.yaml: |-
    receivers:
      # Per-container/pod/node CPU, memory, network, filesystem, volume
      # metrics scraped from the local node's kubelet.
      kubeletstats:
        collection_interval: 30s
        auth_type: serviceAccount
        endpoint: "https://${env:KUBE_NODE_NAME}:10250"
        # On managed clusters (EKS/GKE/AKS) the kubelet certificate is usually
        # signed by a CA the ServiceAccount token trusts and you can leave this
        # off. On kind/minikube/k3s the kubelet often uses a self-signed cert
        # and you need this set to true. It bypasses TLS verification of the
        # kubelet — fine on a node-local connection, less so over the network.
        insecure_skip_verify: true
        metric_groups: [node, pod, container, volume]
        extra_metadata_labels:
          - container.id
          - k8s.volume.type

      # Tails container stdout/stderr written by the container runtime to
      # /var/log/pods/<namespace>_<pod>_<uid>/<container>/<n>.log.
      filelog:
        include_file_path: true
        include:
          - /var/log/pods/*/*/*.log
        exclude:
          # Don't scrape our own logs — would loop.
          - /var/log/pods/observability_otel-node-collector-*/*/*.log
          - /var/log/pods/observability_otel-cluster-collector-*/*/*.log
        start_at: end
        operators:
          # Parses CRI/Docker container log format, extracts the actual log
          # body, and adds k8s.pod.name, k8s.namespace.name, k8s.container.name
          # from the file path.
          - id: container-parser
            type: container
          # Apps that log JSON: parse it and lift fields to attributes.
          - id: json_parser
            type: json_parser
            if: 'hasPrefix(body, "{\"")'
            parse_from: body
            parse_to: attributes
            parse_ints: true
            timestamp:
              parse_from: attributes.timestamp
              layout_type: strptime
              layout: "%Y-%m-%dT%H:%M:%S.%f%z"
            severity:
              parse_from: attributes.level
              overwrite_text: true

      # Node-level metrics from /proc and /sys, mounted from the host.
      # Optional — skip this receiver and its volume mounts if you don't want it.
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

      # Apps on this node send OTLP here. Enriching at the agent (not at a
      # central gateway) means k8sattributesprocessor sees the connection IP
      # of the sending pod, which is the simplest way to attach k8s metadata.
      otlp:
        protocols:
          grpc:
            endpoint: 0.0.0.0:4317
          http:
            endpoint: 0.0.0.0:4318

    processors:
      # Limits pod-watch to this node only via the downward-API env var.
      # Without filter.node, every DaemonSet replica would watch every pod
      # cluster-wide — N nodes watching N pods.
      k8sattributes:
        auth_type: serviceAccount
        passthrough: false
        filter:
          node_from_env_var: KUBE_NODE_NAME
        extract:
          metadata:
            - k8s.cluster.uid
            - k8s.namespace.name
            - k8s.pod.name
            - k8s.pod.uid
            - k8s.pod.start_time
            - k8s.deployment.name
            - k8s.statefulset.name
            - k8s.daemonset.name
            - k8s.cronjob.name
            - k8s.job.name
            - k8s.node.name
            - k8s.container.name
            - container.image.name
            - container.image.tag
            - container.id
        pod_association:
          # For OTLP from apps: the connection IP is the sending pod's IP.
          - sources:
              - from: connection
          # For filelog: the container operator sets k8s.pod.uid on logs.
          - sources:
              - from: resource_attribute
                name: k8s.pod.uid
          # For kubeletstats: the receiver sets k8s.pod.ip.
          - sources:
              - from: resource_attribute
                name: k8s.pod.ip

      # Add k8s.node.name and k8s.cluster.name to everything from this Collector.
      resource:
        attributes:
          - key: k8s.node.name
            value: "${env:KUBE_NODE_NAME}"
            action: upsert
          - key: k8s.cluster.name
            value: "${env:K8S_CLUSTER_NAME}"
            action: upsert

      batch:
        send_batch_size: 1000
        timeout: 5s

    exporters:
      otlphttp:
        endpoint: "https://logfire-eu.pydantic.dev"
        headers:
          Authorization: "Bearer ${env:LOGFIRE_TOKEN}"

    service:
      pipelines:
        metrics:
          receivers: [kubeletstats, hostmetrics, otlp]
          processors: [k8sattributes, resource, batch]
          exporters: [otlphttp]
        logs:
          receivers: [filelog, otlp]
          processors: [k8sattributes, resource, batch]
          exporters: [otlphttp]
        traces:
          receivers: [otlp]
          processors: [k8sattributes, resource, batch]
          exporters: [otlphttp]
```

### DaemonSet

```yaml title="node-collector.yaml"
apiVersion: apps/v1
kind: DaemonSet
metadata:
  name: otel-node-collector
  namespace: observability
  labels:
    app: otel-collector
    component: node
spec:
  selector:
    matchLabels:
      app: otel-collector
      component: node
  template:
    metadata:
      labels:
        app: otel-collector
        component: node
    spec:
      serviceAccountName: otel-collector
      # `hostPort` on the OTLP listeners makes the receiver reachable from
      # apps on the same node via the host IP; filelog and hostmetrics get
      # node-level files via the hostPath volume mounts below. Neither
      # requires hostNetwork, so we keep the pod in its own netns.
      hostNetwork: false
      containers:
        - name: otel-collector
          image: otel/opentelemetry-collector-contrib:0.128.0
          args: ["--config=/etc/otelcol-contrib/config.yaml"]
          env:
            - name: LOGFIRE_TOKEN
              valueFrom:
                secretKeyRef:
                  name: logfire-token
                  key: logfire-token
            # The downward API: gives kubeletstats and k8sattributes the
            # name of the node this Pod is running on. Without it,
            # filter.node_from_env_var has nothing to read.
            - name: KUBE_NODE_NAME
              valueFrom:
                fieldRef:
                  fieldPath: spec.nodeName
            # Set this manually per-cluster, or pull it from a ConfigMap.
            - name: K8S_CLUSTER_NAME
              value: "my-cluster"
          ports:
            - name: otlp-grpc
              containerPort: 4317
              hostPort: 4317
            - name: otlp-http
              containerPort: 4318
              hostPort: 4318
          resources:
            requests:
              cpu: 100m
              memory: 256Mi
            limits:
              cpu: 500m
              memory: 512Mi
          volumeMounts:
            - mountPath: /etc/otelcol-contrib/config.yaml
              name: config
              subPath: config.yaml
              readOnly: true
            # Pod log files written by the container runtime.
            - mountPath: /var/log/pods
              name: varlogpods
              readOnly: true
            # Symlink targets — varlogpods entries are symlinks into this dir
            # on Docker-based runtimes.
            - mountPath: /var/lib/docker/containers
              name: varlibdockercontainers
              readOnly: true
            # Host /proc and /sys for hostmetrics (root_path: /host).
            - mountPath: /host
              name: hostfs
              readOnly: true
              mountPropagation: HostToContainer
      volumes:
        - name: config
          configMap:
            name: otel-node-collector-config
        - name: varlogpods
          hostPath:
            path: /var/log/pods
        - name: varlibdockercontainers
          hostPath:
            path: /var/lib/docker/containers
        - name: hostfs
          hostPath:
            path: /
```

```shell
kubectl apply -f node-collector-config.yaml
kubectl apply -f node-collector.yaml
```

A few things worth calling out:

- **`KUBE_NODE_NAME` from the downward API** is what makes everything node-local. `kubeletstats` uses it to build the kubelet URL (`https://<this-node>:10250`); `k8sattributesprocessor` uses it via `filter.node_from_env_var` to watch only pods on this node instead of every pod in the cluster.
- **`insecure_skip_verify: true`** on `kubeletstats` is the easy path. Drop it on managed clusters once you've confirmed the kubelet cert is trusted by your ServiceAccount token. On kind/minikube/k3s with default settings, you'll usually need it. The connection is node-local so the risk is limited, but it does mean the Collector won't notice if a malicious workload on the node MITMs the kubelet.
- **`hostPort` on 4317/4318** lets app Pods on the same node send OTLP to `$(HOST_IP):4317` without going through a Service. This is the simplest way for `k8sattributesprocessor` to see the real source IP of the sending pod, which is how it correlates incoming OTLP to a Kubernetes pod.
- **`exclude` in `filelog`** must list both Collector workloads. Otherwise the Collector tails its own logs, ships them to Logfire, and you've built an infinite loop with a delay.

!!! note "Why enrich at the DaemonSet, not at a central gateway?"
    If you run a central Collector gateway and forward everything to it, the gateway sees the agent's IP, not the original sending pod's IP. You'd need to either run `k8sattributesprocessor` at the agent in `passthrough: true` mode (which annotates with the pod IP but doesn't call the K8s API) and then again at the gateway in default mode, or use `pod_association` rules that match on `k8s.pod.ip` set explicitly. The single-agent layout above is simpler and works for most clusters.

## How the pieces fit together

Once both manifests are applied, four streams of data flow to Logfire:

| Stream | Source | Pipeline |
|--------|--------|----------|
| Cluster state metrics | `k8sclusterreceiver` (cluster Deployment) | `metrics` |
| Kubernetes Events as logs | `k8sobjectsreceiver` (cluster Deployment) | `logs` |
| Container CPU/mem/net/disk + host metrics | `kubeletstats` + `hostmetrics` (DaemonSet) | `metrics` |
| Pod stdout/stderr | `filelog` (DaemonSet) | `logs` |
| Your apps' OTLP | `otlp` (DaemonSet) | `traces`, `metrics`, `logs` |

Every stream is enriched by `k8sattributesprocessor` with `k8s.cluster.name`, `k8s.node.name`, `k8s.namespace.name`, `k8s.pod.name`, `k8s.deployment.name`, etc. before it leaves the Collector — which is what makes the Logfire UI able to group, filter, and roll up by Kubernetes object.

## Step-by-step walkthrough: pod logs from a fresh cluster

The rest of this section is a hands-on walkthrough you can paste verbatim into a fresh local cluster. It focuses on the *pod logs* slice — the smallest interesting subset — and is the easiest way to confirm the moving parts work before turning on cluster metrics and kubeletstats.

To follow this guide you'll need a local Kubernetes cluster running. Options include [Docker Desktop](https://www.docker.com/blog/how-to-set-up-a-kubernetes-cluster-on-docker-desktop/), [Rancher Desktop](https://docs.rancherdesktop.io/), [Minikube](https://minikube.sigs.k8s.io/docs/start/?arch=%2Fmacos%2Farm64%2Fstable%2Fbinary+download), [Kind](https://kind.sigs.k8s.io/), or [k3s](https://docs.k3s.io/quick-start).

### 1. Deploy two demo apps

`apps.yaml` defines a plain-text and a JSON logger so you can see the difference in how the Collector handles each:

```yaml title="apps.yaml"
apiVersion: apps/v1
kind: Deployment
metadata:
  name: plain-app
  namespace: default
  labels:
    app: plain-app
spec:
  replicas: 1
  selector:
    matchLabels:
      app: plain-app
  template:
    metadata:
      labels:
        app: plain-app
    spec:
      terminationGracePeriodSeconds: 1
      containers:
        - name: plain-app
          image: busybox
          command: ["sh", "-c", "while true; do echo 'Hello World'; sleep 1; done"]
          resources:
            limits:
              memory: "64Mi"
              cpu: "500m"
            requests:
              memory: "64Mi"
              cpu: "500m"
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: json-app
  namespace: default
  labels:
    app: json-app
spec:
  replicas: 1
  selector:
    matchLabels:
      app: json-app
  template:
    metadata:
      labels:
        app: json-app
    spec:
      terminationGracePeriodSeconds: 1
      containers:
        - name: json-app
          image: busybox
          command:
            - "sh"
            - "-c"
            - |
              while true; do
                now=$(date -u '+%Y-%m-%dT%H:%M:%SZ')
                echo "{\"message\":\"Hello world!\",\"level\":\"warn\",\"timestamp\":\"$now\"}"
                sleep 1
              done
          resources:
            limits:
              memory: "64Mi"
              cpu: "500m"
            requests:
              memory: "64Mi"
              cpu: "500m"
```

```shell
kubectl apply -f apps.yaml
```

### 2. Apply the RBAC, Secret, and DaemonSet

Reuse `rbac.yaml`, `secrets.yaml`, and `node-collector.yaml` from above. If you only care about pod logs for this walkthrough, the following stripped-down Collector config is enough — it skips kubeletstats and hostmetrics:

```yaml title="logs-only-collector-config.yaml"
apiVersion: v1
kind: ConfigMap
metadata:
  name: otel-node-collector-config
  namespace: observability
data:
  config.yaml: |-
    receivers:
      filelog:
        include_file_path: true
        include:
          - /var/log/pods/*/*/*.log
        exclude:
          - /var/log/pods/observability_otel-node-collector-*/*/*.log
        operators:
          - id: container-parser
            type: container
          - id: json_parser
            type: json_parser
            if: 'hasPrefix(body, "{\"")'
            parse_from: body
            parse_to: attributes
            parse_ints: true
            timestamp:
              parse_from: attributes.timestamp
              layout_type: strptime
              layout: "%Y-%m-%dT%H:%M:%S.%f%z"
            severity:
              parse_from: attributes.level
              overwrite_text: true
    processors:
      k8sattributes:
        auth_type: serviceAccount
        filter:
          node_from_env_var: KUBE_NODE_NAME
        extract:
          metadata:
            - k8s.namespace.name
            - k8s.pod.name
            - k8s.deployment.name
            - k8s.node.name
            - k8s.container.name
        pod_association:
          - sources:
              - from: resource_attribute
                name: k8s.pod.uid
      batch:
    exporters:
      debug:
      otlphttp:
        endpoint: "https://logfire-eu.pydantic.dev"
        headers:
          Authorization: "Bearer ${env:LOGFIRE_TOKEN}"
    service:
      pipelines:
        logs:
          receivers: [filelog]
          processors: [k8sattributes, batch]
          exporters: [debug, otlphttp]
```

### 3. Watch it work

```shell
kubectl -n observability logs -l app=otel-collector,component=node -f
```

The `debug` exporter prints each batch to the Collector's own stdout. You should see log records from both `plain-app` and `json-app` flowing through, the JSON one already parsed into attributes (`message`, `level`, `timestamp` lifted out of `body`).

In the Logfire UI, the same records appear in the **Live** view tagged with `k8s.pod.name`, `k8s.namespace.name`, `k8s.deployment.name`, and `k8s.container.name`. Group by any of these on the **Kubernetes** page.

## What `k8sattributesprocessor` actually does

This processor is the glue that turns "the Collector saw a span/log/metric" into "the Collector saw a span/log/metric *from this Pod, in this Deployment, on this Node*."

By default it discovers the source Pod in one of two ways:

- **Connection IP** — when an app sends OTLP over the network, the processor takes the source IP from the connection and looks up the matching pod via the Kubernetes API (or a local cache). This works as long as the Pod's IP isn't NAT'd away. Running the Collector as a DaemonSet on the same node as the app, with `hostPort` on the OTLP receiver, is the layout where this works most reliably — the app's source IP arrives unchanged.
- **Resource attributes** — if the telemetry already has `k8s.pod.uid`, `k8s.pod.ip`, or `k8s.pod.name` set (e.g. set by `filelog`'s container operator, or by `kubeletstatsreceiver`, or by the SDK via the OTel resource detector), the processor matches on those instead. Configure this with `pod_association`.

The first matching `pod_association` rule wins.

Two modes are available:

- **`passthrough: false` (default)** — the processor calls the Kubernetes API and enriches the telemetry with the full set of attributes you listed under `extract.metadata`. This is what you want at the agent that owns the data.
- **`passthrough: true`** — the processor only annotates the data with the pod IP and does *not* call the Kubernetes API. Used when a collector in agent mode forwards to a central gateway, and the gateway runs the full processor. This keeps the API-watch load on one place.

Three things you'll forget the first time:

1. The DaemonSet needs `KUBE_NODE_NAME` from the downward API; without it `filter.node_from_env_var` returns empty and the processor watches *every* pod cluster-wide. On a 500-node cluster, that's a real problem.
2. `k8s.deployment.name` comes from walking pod → replicaset → deployment. You need read access to `replicasets`, even if you don't extract `k8s.replicaset.name`.
3. `k8s.cluster.uid` only resolves with cluster-scoped RBAC, not a namespaced `Role`.

## Verifying it works on the Logfire side

Once both Collectors are running:

1. Open the **Kubernetes** page in the Logfire UI. It groups by `k8s.cluster.name`, `k8s.node.name`, `k8s.namespace.name`, and `k8s.pod.name`. If your Pods aren't appearing, `k8sattributesprocessor` likely isn't enriching them — check the Collector's own logs and the RBAC ClusterRole.
2. Open **Metrics** and look for `k8s.pod.cpu.utilization`, `k8s.pod.memory.working_set`, `k8s.node.cpu.utilization`, `k8s.container.cpu.usage`, `k8s.deployment.available`, `k8s.deployment.desired`. The first three come from `kubeletstats`; the deployment ones come from `k8sclusterreceiver`.
3. Open **Live** and filter for `otel_resource_attributes->>'k8s.namespace.name' = 'default'`. You should see your apps' stdout flowing through.
4. Query Kubernetes Events with SQL:

    ```sql
    SELECT
      attributes->>'k8s.event.reason' AS reason,
      attributes->>'k8s.event.action' AS action,
      otel_resource_attributes->>'k8s.namespace.name' AS namespace,
      message
    FROM records
    WHERE otel_resource_attributes->>'k8s.cluster.name' = 'my-cluster'
      AND attributes->>'k8s.event.reason' IS NOT NULL
    ORDER BY timestamp DESC
    LIMIT 100
    ```

5. Find unhandled exceptions, scoped to a namespace:

    ```sql
    SELECT exception_message
    FROM records
    WHERE is_exception = true
      AND otel_resource_attributes->>'k8s.namespace.name' = 'default'
    ```

If nothing appears, the usual suspects in order:

- **Token wrong region.** The `endpoint` must match the project's region (`logfire-eu` vs `logfire-us`).
- **RBAC missing a verb.** `kubectl -n observability logs deploy/otel-cluster-collector` and `kubectl -n observability logs ds/otel-node-collector` — the receivers log "forbidden" errors loudly.
- **`KUBE_NODE_NAME` not injected.** `kubectl -n observability exec ds/otel-node-collector -- env | grep KUBE_NODE_NAME` should print a node name.
- **`kubeletstats` TLS errors.** On kind/minikube/k3s set `insecure_skip_verify: true`. On managed clusters check that the ServiceAccount token signs the kubelet's serving cert.
- **`filelog` finds no files.** `kubectl -n observability exec ds/otel-node-collector -- ls /var/log/pods` should list your pods. If empty, the host path may be different (e.g. on Talos or some MicroK8s setups).

## Further reading

- [`k8sclusterreceiver` README](https://github.com/open-telemetry/opentelemetry-collector-contrib/tree/main/receiver/k8sclusterreceiver) — full list of metrics, including the ones disabled by default.
- [`kubeletstatsreceiver` README](https://github.com/open-telemetry/opentelemetry-collector-contrib/tree/main/receiver/kubeletstatsreceiver) — `auth_type` options, `metric_groups`, and the volume-metric attributes.
- [`k8sobjectsreceiver` README](https://github.com/open-telemetry/opentelemetry-collector-contrib/tree/main/receiver/k8sobjectsreceiver) — collecting arbitrary objects beyond Events, and pull vs. watch modes.
- [`k8sattributesprocessor` README](https://github.com/open-telemetry/opentelemetry-collector-contrib/tree/main/processor/k8sattributesprocessor) — every extractable attribute and the full `pod_association` syntax.
- [`filelogreceiver` README](https://github.com/open-telemetry/opentelemetry-collector-contrib/tree/main/receiver/filelogreceiver) and the [container operator](https://github.com/open-telemetry/opentelemetry-collector-contrib/blob/main/pkg/stanza/docs/operators/container.md) — for advanced log parsing.
- [OpenTelemetry Collector on Kubernetes](https://opentelemetry.io/docs/platforms/kubernetes/collector/components) — upstream deployment-pattern reference (sidecar / DaemonSet / Deployment / Gateway).
- [Advanced scrubbing with the OTel Collector](./otel-collector-scrubbing.md) — if you need to redact PII before it leaves the cluster.
