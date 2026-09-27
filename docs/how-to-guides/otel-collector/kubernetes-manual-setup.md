---
title: "Build a custom Kubernetes Collector deployment"
description: "Deploy cluster-scoped and per-node OpenTelemetry Collectors for Kubernetes infrastructure without the Helm chart."
---
# Build a custom Kubernetes Collector deployment

Deploy a two-Collector Kubernetes layout that sends cluster state, node metrics, pod logs, and Kubernetes Events to Logfire.

The OpenTelemetry (OTel) Collector is a separate program that gathers traces, metrics, and logs and forwards them to Logfire. Use this reference when you need to own the Kubernetes manifests or customize beyond the supported Helm chart. For the normal setup, use [Kubernetes monitoring with Helm](kubernetes-monitoring.md).

!!! caution "You own this deployment"
    These manifests expose more deployment details than the Helm setup and require you to maintain Collector versions, role-based access control (RBAC), which controls access by role, rollout behavior, and log mounts. Start with the Helm setup unless your cluster requires this control.

## The two-Collector pattern

A single Collector workload cannot collect everything in Kubernetes cleanly. Some receivers describe the cluster as a whole, and some describe a node from the inside. Mixing the two in one deployment either duplicates data N times across N nodes or misses node-local data entirely.

The recommended layout is two Collector workloads sharing one image, one config schema, and one ServiceAccount:

- **Cluster-scoped Collector**: a `Deployment` with **exactly one replica**. Runs:
    - [`k8sclusterreceiver`](https://github.com/open-telemetry/opentelemetry-collector-contrib/tree/main/receiver/k8sclusterreceiver): node count, pod phases, deployment/daemonset replica status, allocatable resources. Talks to the API server, not the nodes. Running this on every node would multiply every metric by N.
    - [`k8sobjectsreceiver`](https://github.com/open-telemetry/opentelemetry-collector-contrib/tree/main/receiver/k8sobjectsreceiver): Kubernetes Events (pod scheduling, out-of-memory kills, image pull failures, and similar events) as log records. The upstream README is explicit: "This receiver must be deployed as one replica, otherwise it'll be producing duplicated data."
    - [`k8sattributesprocessor`](https://github.com/open-telemetry/opentelemetry-collector-contrib/tree/main/processor/k8sattributesprocessor): to enrich the cluster-scoped data with namespace/workload attributes before exporting.

- **Per-node Collector**: a `DaemonSet`, one Pod per node. Runs:
    - [`kubeletstatsreceiver`](https://github.com/open-telemetry/opentelemetry-collector-contrib/tree/main/receiver/kubeletstatsreceiver): talks to the local node's kubelet on `https://<node>:10250/stats/summary` and emits container/pod/node CPU, memory, network, filesystem, volume metrics. Must run on every node; can only see its own node.
    - [`file_log`](https://github.com/open-telemetry/opentelemetry-collector-contrib/tree/main/receiver/filelogreceiver): tails `/var/log/pods/*/*/*.log` to ship pod stdout/stderr. Only readable from a host-mounted volume on the node itself.
    - Optionally [`host_metrics`](https://github.com/open-telemetry/opentelemetry-collector-contrib/tree/main/receiver/hostmetricsreceiver) with `root_path: /host`: node-level CPU, load, paging, processes from `/proc` and `/sys`.
    - `k8sattributesprocessor` with `filter.node_from_env_var: KUBE_NODE_NAME`: to enrich everything with pod/workload metadata while only watching pods on the local node.

!!! tip "Mental model"
    *"Things about the cluster"* → one Deployment.
    *"Things about a node, or logs written by Pods on a node"* → DaemonSet.

The two share one ClusterRole and one ServiceAccount because the receivers and processor want the same set of read permissions on the Kubernetes API.

## Prerequisites: write token and namespace

We'll deploy everything into a dedicated `observability` namespace and read the Logfire write token from a Secret.

```shell
kubectl create namespace observability
```

Create a Logfire write token (see [Create Write Tokens](../create-write-tokens.md)) and store it as a Secret:

```shell
printf 'Paste your Logfire write token: '
read -r -s LOGFIRE_WRITE_TOKEN
printf '\n'
printf '%s' "$LOGFIRE_WRITE_TOKEN" | kubectl -n observability create secret generic logfire-token \
  --from-file=logfire-token=/dev/stdin
unset LOGFIRE_WRITE_TOKEN
```

In production prefer a real secrets manager, for example [External Secrets Operator](https://external-secrets.io/latest/) syncing from AWS Secrets Manager, GCP Secret Manager, or Vault.

## RBAC: one ClusterRole for both Collectors

Both the Deployment and the DaemonSet authenticate as the same `otel-collector` ServiceAccount. The ClusterRole below is the union of what all four components (`k8sclusterreceiver`, `k8sobjectsreceiver`, `kubeletstatsreceiver`, `k8sattributesprocessor`) need. It's all read-only: `get`, `list`, `watch`.

```yaml title="rbac.yaml" collapse="10"
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
  # Core resources: used by all four components.
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

These manifests require cluster-scoped RBAC. A namespaced `Role` is not a drop-in replacement: `kubeletstatsreceiver` needs `nodes/stats`, `k8sclusterreceiver` watches nodes and namespaces, and both `k8sattributesprocessor` instances watch pods. A namespace-only design requires coordinated receiver filters, processor filters, and namespaced bindings, and it cannot provide the complete Logfire Kubernetes page. Do not substitute a `Role` in this recipe.

## Cluster-scoped Collector (Deployment)

This is the single-replica Collector that talks to the API server and ships cluster state plus Kubernetes Events.

### Config

```yaml title="cluster-collector-config.yaml" collapse="10"
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
        collection_interval: 60s
        node_conditions_to_report: [Ready, MemoryPressure, DiskPressure]
        allocatable_types_to_report: [cpu, memory]

      # Kubernetes Events as OTel log records.
      # Watch mode keeps a long-lived connection open; pull mode polls.
      k8s_objects:
        auth_type: serviceAccount
        objects:
          - name: events
            mode: watch
            group: events.k8s.io

    processors:
      # Apply backpressure before enrichment or batching approaches the Pod limit.
      memory_limiter:
        check_interval: 1s
        limit_percentage: 80
        spike_limit_percentage: 20

      # Use the same stable name in both Collector deployments.
      resource:
        attributes:
          - key: k8s.cluster.name
            value: "${env:K8S_CLUSTER_NAME}"
            action: upsert

      # Enrich namespace-scoped metrics with workload metadata.
      # This Collector is a Deployment, not a DaemonSet, so we do NOT filter by node.
      k8s_attributes:
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
      otlp_http:
        # US:  https://logfire-us.pydantic.dev
        # EU:  https://logfire-eu.pydantic.dev
        endpoint: "https://logfire-us.pydantic.dev" # or https://logfire-eu.pydantic.dev
        headers:
          Authorization: "Bearer ${env:LOGFIRE_TOKEN}"

    service:
      pipelines:
        metrics:
          receivers: [k8s_cluster]
          processors: [memory_limiter, k8s_attributes, resource, batch]
          exporters: [otlp_http]
        logs:
          receivers: [k8s_objects]
          processors: [memory_limiter, k8s_attributes, resource, batch]
          exporters: [otlp_http]
```

### Deployment

```yaml title="cluster-collector.yaml" collapse="10"
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
          image: otel/opentelemetry-collector-contrib:0.154.0
          args: ["--config=/etc/otelcol-contrib/config.yaml"]
          env:
            # 80% of the 512 MiB container limit below.
            - name: GOMEMLIMIT
              value: "410MiB"
            - name: LOGFIRE_TOKEN
              valueFrom:
                secretKeyRef:
                  name: logfire-token
                  key: logfire-token
            - name: K8S_CLUSTER_NAME
              value: "my-cluster"
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

This Collector runs once per node and is the workhorse for kubelet metrics, pod logs, and optional host metrics.

### Config

```yaml title="node-collector-config.yaml" collapse="10"
apiVersion: v1
kind: ConfigMap
metadata:
  name: otel-node-collector-config
  namespace: observability
data:
  config.yaml: |-
    extensions:
      file_storage:
        directory: /var/lib/otelcol/file_storage

    receivers:
      # Per-container/pod/node CPU, memory, network, and filesystem
      # metrics scraped from the local node's kubelet.
      kubelet_stats:
        collection_interval: 60s
        auth_type: serviceAccount
        endpoint: "https://${env:KUBE_NODE_NAME}:10250"
        # serviceAccount verifies the kubelet certificate with the cluster's
        # certificate authority (CA). Set ca_file when the kubelet uses another CA.
        metric_groups: [node, pod, container, volume]
        extra_metadata_labels:
          - container.id

      # Tails container stdout/stderr written by the container runtime to
      # /var/log/pods/<namespace>_<pod>_<uid>/<container>/<n>.log.
      file_log:
        include_file_path: true
        include:
          - /var/log/pods/*/*/*.log
        exclude:
          # Don't scrape our own logs: would loop.
          - /var/log/pods/observability_otel-node-collector-*/*/*.log
          - /var/log/pods/observability_otel-cluster-collector-*/*/*.log
        start_at: end
        storage: file_storage
        operators:
          # Parses Container Runtime Interface (CRI) or Docker log format,
          # extracts the body, and adds pod, namespace, and container identity
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
              layout: "%Y-%m-%dT%H:%M:%S%z"
            severity:
              parse_from: attributes.level
              overwrite_text: true

      # Node-level metrics from /proc and /sys, mounted from the host.
      # To omit them, remove this receiver, `host_metrics` from the metrics
      # pipeline, and the hostfs mount and volume from the DaemonSet.
      host_metrics:
        collection_interval: 60s
        root_path: /host
        scrapers:
          cpu:
          memory:
          load:
          disk:
            exclude:
              devices: ['^(loop|ram)[0-9]+$']
              match_type: regexp
          filesystem:
            # Pod volume mounts are high-cardinality and can contain paths the
            # Collector user cannot read. kubelet_stats covers pod volumes.
            exclude_mount_points:
              mount_points: ['^/var/lib/kubelet/pods/.*']
              match_type: regexp
            include_virtual_filesystems: false
          network:
            exclude:
              interfaces: [lo, 'veth.*']
              match_type: regexp
          paging:

    processors:
      # Apply backpressure before enrichment or batching approaches the Pod limit.
      memory_limiter:
        check_interval: 1s
        limit_percentage: 80
        spike_limit_percentage: 20

      # Limits pod-watch to this node only via the downward-API env var.
      # Without filter.node, every DaemonSet replica would watch every pod
      # cluster-wide: N nodes watching N pods.
      k8s_attributes:
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
          # For file_log: the container operator sets k8s.pod.uid on logs.
          - sources:
              - from: resource_attribute
                name: k8s.pod.uid
          # For kubelet_stats: the receiver sets k8s.pod.ip.
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
      otlp_http:
        endpoint: "https://logfire-us.pydantic.dev" # or https://logfire-eu.pydantic.dev
        headers:
          Authorization: "Bearer ${env:LOGFIRE_TOKEN}"

    service:
      extensions: [file_storage]
      pipelines:
        metrics:
          receivers: [kubelet_stats, host_metrics]
          processors: [memory_limiter, k8s_attributes, resource, batch]
          exporters: [otlp_http]
        logs:
          receivers: [file_log]
          processors: [memory_limiter, k8s_attributes, resource, batch]
          exporters: [otlp_http]
```

### DaemonSet

```yaml title="node-collector.yaml" collapse="10"
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
      # Collect from control-plane nodes when they use the standard taints.
      tolerations:
        - key: node-role.kubernetes.io/control-plane
          operator: Exists
          effect: NoSchedule
        - key: node-role.kubernetes.io/master
          operator: Exists
          effect: NoSchedule
      # file_log and host_metrics get node-level files through the hostPath
      # mounts below. Neither requires hostNetwork, so the Pod keeps its own
      # network namespace and exposes no ingest port on the node.
      hostNetwork: false
      initContainers:
        - name: prepare-file-storage
          image: busybox:1.36.1
          command: ["sh", "-c", "chown -R 10001:10001 /var/lib/otelcol/file_storage"]
          securityContext:
            runAsUser: 0
          volumeMounts:
            - mountPath: /var/lib/otelcol/file_storage
              name: file-storage
      containers:
        - name: otel-collector
          image: otel/opentelemetry-collector-contrib:0.154.0
          args: ["--config=/etc/otelcol-contrib/config.yaml"]
          env:
            # 80% of the 512 MiB container limit below.
            - name: GOMEMLIMIT
              value: "410MiB"
            - name: LOGFIRE_TOKEN
              valueFrom:
                secretKeyRef:
                  name: logfire-token
                  key: logfire-token
            # The downward API: gives kubelet_stats and k8s_attributes the
            # name of the node this Pod is running on. Without it,
            # filter.node_from_env_var has nothing to read.
            - name: KUBE_NODE_NAME
              valueFrom:
                fieldRef:
                  fieldPath: spec.nodeName
            # Set this manually per-cluster, or pull it from a ConfigMap.
            - name: K8S_CLUSTER_NAME
              value: "my-cluster"
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
            # Persist file_log offsets on this node across Collector restarts.
            - mountPath: /var/lib/otelcol/file_storage
              name: file-storage
            # Host /proc and /sys for host_metrics (root_path: /host).
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
        - name: file-storage
          hostPath:
            path: /var/lib/otelcol/file_storage
            type: DirectoryOrCreate
        - name: hostfs
          hostPath:
            path: /
```

!!! note "Local clusters (kind, minikube, and k3s)"
    If the kubelet certificate is not signed by the cluster certificate authority mounted with the ServiceAccount, `kubelet_stats` reports an `x509: certificate signed by unknown authority` error. `kind` does this by default. For a local development cluster, add `insecure_skip_verify: true` beside the `kubelet_stats` `endpoint` before applying the configuration. Do not carry that exception into production; provide the kubelet certificate's issuing authority with `ca_file` instead.

```shell
kubectl apply -f node-collector-config.yaml
kubectl apply -f node-collector.yaml
```

A few things worth calling out:

- **`KUBE_NODE_NAME` from the downward API** is what makes everything node-local. `kubelet_stats` uses it to build the kubelet URL (`https://<this-node>:10250`); `k8sattributesprocessor` uses it via `filter.node_from_env_var` to watch only pods on this node instead of every pod in the cluster.
- **Kubelet TLS verification** uses the cluster certificate authority with `auth_type: serviceAccount`. If the kubelet certificate has a different issuer, mount that certificate and set `ca_file`. Only use `insecure_skip_verify: true` for an explicit local development exception such as kind, minikube, or k3s; it sends the ServiceAccount bearer token without verifying the kubelet's identity.
- **[`memory_limiter`](https://github.com/open-telemetry/opentelemetry-collector/tree/main/processor/memorylimiterprocessor) and [`GOMEMLIMIT`](https://pkg.go.dev/runtime#hdr-Environment_Variables)** both use 80% of the example's 512 MiB container limit. The processor applies backpressure before the Collector reaches its limit, while the Go runtime starts collecting memory more aggressively. Treat the CPU and memory requests and limits as starting values for a small cluster; monitor the Collector and keep both safeguards aligned with the container's memory limit as you tune it for your data volume.
- **`file_storage`** keeps each node's `file_log` offsets under `/var/lib/otelcol/file_storage`, so a restarted Collector resumes instead of skipping logs written while it was down. The root init container only makes that host directory writable by the Collector image's pinned user ID, `10001`.
- **`exclude` in `file_log`** must list both Collector workloads. Otherwise the Collector tails its own logs, ships them to Logfire, and you've built an infinite loop with a delay.

!!! note "Application telemetry is separate"
    This infrastructure recipe intentionally exposes no OpenTelemetry Protocol (OTLP) ingest port. Send application telemetry directly to Logfire, or design a Collector gateway with TLS, receiver authentication, and Kubernetes NetworkPolicies that restrict which workloads can reach it. Do not add an unauthenticated `hostPort` to this DaemonSet.

## How the pieces fit together

Once both manifests are applied, four streams of data flow to Logfire:

| Stream | Source | Pipeline |
|--------|--------|----------|
| Cluster state metrics | `k8sclusterreceiver` (cluster Deployment) | `metrics` |
| Kubernetes Events as logs | `k8sobjectsreceiver` (cluster Deployment) | `logs` |
| Container CPU, memory, network, and disk plus host metrics | `kubelet_stats` + `host_metrics` (DaemonSet) | `metrics` |
| Pod stdout/stderr | `file_log` (DaemonSet) | `logs` |

Before pod-associated metrics and logs leave the Collector, `k8sattributesprocessor` adds pod, workload, and node identity. Kubernetes Event records keep the involved object in their structured body and expose the namespace. The `resource` processor adds the stable cluster name to every stream. Together, these fields let the Logfire UI group pod-associated signals by cluster, node, namespace, pod, and workload, while Events remain searchable by cluster and namespace.

## Step-by-step walkthrough: pod logs from a fresh cluster

The rest of this section is a hands-on walkthrough you can paste verbatim into a fresh local cluster. It focuses on the *pod logs* slice (the smallest interesting subset), providing a focused check of the moving parts before you turn on cluster metrics and `kubelet_stats`.

To follow this guide you'll need a local Kubernetes cluster running. Options include [Docker Desktop](https://www.docker.com/blog/how-to-set-up-a-kubernetes-cluster-on-docker-desktop/), [Rancher Desktop](https://docs.rancherdesktop.io/), [Minikube](https://minikube.sigs.k8s.io/docs/start/?arch=%2Fmacos%2Farm64%2Fstable%2Fbinary+download), [Kind](https://kind.sigs.k8s.io/), or [k3s](https://docs.k3s.io/quick-start).

### 1. Deploy two demo apps

`apps.yaml` defines a plain-text and a JSON logger so you can see the difference in how the Collector handles each:

```yaml title="apps.yaml" collapse="10"
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
          image: busybox:1.36.1
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
          image: busybox:1.36.1
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

Save `rbac.yaml`, `cluster-collector-config.yaml`, `cluster-collector.yaml`, `node-collector-config.yaml`, and `node-collector.yaml` from above before continuing. The commands below create the namespace, ServiceAccount, permissions, and Secret required on a fresh cluster. If you only care about pod logs for this walkthrough, the following stripped-down Collector config is enough; it skips `kubelet_stats` and `host_metrics`. Keep the full Collector manifests unchanged so you can restore them later.

```yaml title="logs-only-collector-config.yaml" collapse="10"
apiVersion: v1
kind: ConfigMap
metadata:
  name: otel-node-collector-config
  namespace: observability
data:
  config.yaml: |-
    extensions:
      file_storage:
        directory: /var/lib/otelcol/file_storage
    receivers:
      file_log:
        include_file_path: true
        include:
          - /var/log/pods/*/*/*.log
        exclude:
          - /var/log/pods/observability_otel-node-collector-*/*/*.log
          - /var/log/pods/observability_otel-cluster-collector-*/*/*.log
        storage: file_storage
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
              layout: "%Y-%m-%dT%H:%M:%S%z"
            severity:
              parse_from: attributes.level
              overwrite_text: true
    processors:
      memory_limiter:
        check_interval: 1s
        limit_percentage: 80
        spike_limit_percentage: 20
      k8s_attributes:
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
      resource:
        attributes:
          - key: k8s.cluster.name
            value: "${env:K8S_CLUSTER_NAME}"
            action: upsert
      batch:
    exporters:
      debug:
        verbosity: detailed
      otlp_http:
        endpoint: "https://logfire-us.pydantic.dev" # or https://logfire-eu.pydantic.dev
        headers:
          Authorization: "Bearer ${env:LOGFIRE_TOKEN}"
    service:
      extensions: [file_storage]
      pipelines:
        logs:
          receivers: [file_log]
          processors: [memory_limiter, k8s_attributes, resource, batch]
          exporters: [debug, otlp_http]
```

Create the prerequisites, then apply the logs-only ConfigMap. `kubectl patch --local` removes the unused host-root mount before the DaemonSet reaches the API server; the original `node-collector.yaml` stays unchanged.

```shell
kubectl create namespace observability --dry-run=client -o yaml | kubectl apply -f -
kubectl apply -f rbac.yaml

printf 'Paste your Logfire write token: '
read -r -s LOGFIRE_WRITE_TOKEN
printf '\n'
printf '%s' "$LOGFIRE_WRITE_TOKEN" | kubectl -n observability create secret generic logfire-token \
  --from-file=logfire-token=/dev/stdin --dry-run=client -o yaml | kubectl apply -f -
unset LOGFIRE_WRITE_TOKEN

kubectl apply -f logs-only-collector-config.yaml
kubectl patch --local -f node-collector.yaml \
  --type=strategic \
  --patch '{"spec":{"template":{"spec":{"containers":[{"name":"otel-collector","volumeMounts":[{"mountPath":"/host","$patch":"delete"}]}],"volumes":[{"name":"hostfs","$patch":"delete"}]}}}}' \
  -o yaml | kubectl apply -f -
kubectl -n observability rollout status daemonset/otel-node-collector
```

### 3. Watch it work

```shell
kubectl -n observability logs -l app=otel-collector,component=node -f
```

The `debug` exporter prints each batch to the Collector's own stdout. You should see log records from both `plain-app` and `json-app` flowing through, the JSON one already parsed into attributes (`message`, `level`, `timestamp` lifted out of `body`).

In the Logfire UI, the same records appear in the **Live** view tagged with `k8s.pod.name`, `k8s.namespace.name`, `k8s.deployment.name`, and `k8s.container.name`. Group by any of these on the **Kubernetes** page.

## What `k8sattributesprocessor` actually does

This processor is the glue that turns "the Collector saw a span/log/metric" into "the Collector saw a span/log/metric *from this Pod, in this Deployment, on this Node*."

In this configuration it discovers the source Pod from resource attributes. `file_log`'s container operator and `kubeletstatsreceiver` set values such as `k8s.pod.uid` and `k8s.pod.ip`; the processor uses the first matching `pod_association` rule to find the Pod and add the requested metadata.

Two modes are available:

- **`passthrough: false` (default)**: the processor calls the Kubernetes API and enriches the telemetry with the full set of attributes you listed under `extract.metadata`. This is what you want at the agent that owns the data.
- **`passthrough: true`**: the processor only annotates the data with the pod IP and does *not* call the Kubernetes API. Used when a collector in agent mode forwards to a central gateway, and the gateway runs the full processor. This keeps the API-watch load on one place.

Three things you'll forget the first time:

1. The DaemonSet needs `KUBE_NODE_NAME` from the downward API; without it `filter.node_from_env_var` returns empty and the processor watches *every* pod cluster-wide. On a 500-node cluster, that's a real problem.
2. `k8s.deployment.name` comes from walking pod → replicaset → deployment. You need read access to `replicasets`, even if you don't extract `k8s.replicaset.name`.
3. `k8s.cluster.uid` only resolves with cluster-scoped RBAC, not a namespaced `Role`.

## Verify the full deployment in Logfire

The hands-on walkthrough above temporarily replaces the node Collector configuration with its logs-only version. Restore the full configuration before checking metrics and Kubernetes Events. On a local cluster, first make the kubelet TLS adjustment described above if it applies.

```shell
kubectl apply -f cluster-collector-config.yaml
kubectl apply -f cluster-collector.yaml
kubectl apply -f node-collector-config.yaml
kubectl apply -f node-collector.yaml
kubectl -n observability rollout restart daemonset/otel-node-collector
kubectl -n observability rollout status deployment/otel-cluster-collector
kubectl -n observability rollout status daemonset/otel-node-collector
```

Once both full Collectors are running:

1. Open the **Kubernetes** page in the Logfire UI. It groups by `k8s.cluster.name`, `k8s.node.name`, `k8s.namespace.name`, and `k8s.pod.name`. If your Pods aren't appearing, `k8sattributesprocessor` likely isn't enriching them. Check the Collector's own logs and the RBAC ClusterRole.
2. Open **Metrics** and look for `k8s.pod.cpu.usage`, `k8s.pod.memory.usage`, `k8s.node.cpu.usage`, `container.cpu.usage`, `k8s.deployment.available`, `k8s.deployment.desired`. The first four come from `kubelet_stats`; the deployment ones come from `k8sclusterreceiver`.
3. Open **Live** and filter for `otel_resource_attributes->>'k8s.namespace.name' = 'default'`. You should see your apps' stdout flowing through.
4. To inspect Kubernetes Events in **Live**, filter `scope_name` to `github.com/open-telemetry/opentelemetry-collector-contrib/receiver/k8sobjectsreceiver`. Open an event record and inspect `object.reason` and `object.action` in its structured body.
5. Find unhandled exceptions, scoped to a namespace:

    ```sql
    SELECT exception_message
    FROM records
    WHERE is_exception = true
      AND otel_resource_attributes->>'k8s.namespace.name' = 'default'
    ```

If nothing appears, the usual suspects in order:

- **Token wrong region.** The `endpoint` must match the project's region (`logfire-eu` vs `logfire-us`).
- **RBAC missing a verb.** `kubectl -n observability logs deploy/otel-cluster-collector` and `kubectl -n observability logs ds/otel-node-collector`. The receivers log "forbidden" errors loudly.
- **Node name not available.** Check the DaemonSet Pods through the Kubernetes API instead of relying on shell tools in the Collector image:

    ```shell
    kubectl -n observability get pods \
      -l app=otel-collector,component=node \
      -o jsonpath='{range .items[*]}{.metadata.name}{" -> "}{.spec.nodeName}{"\n"}{end}'
    ```

    Every Collector Pod should show its assigned node after the arrow. The downward API copies that value into `KUBE_NODE_NAME`.
- **`kubelet_stats` TLS errors.** For a local development cluster whose kubelet serving certificate does not chain to the mounted cluster CA, use the local-only `insecure_skip_verify: true` exception described above. In production, verify that the kubelet serving certificate chains to the mounted CA or set `ca_file` to its issuing CA; separately confirm that the ServiceAccount can access the kubelet API.
- **`file_log` finds no files.** Inspect the documented host path from a temporary node-debugger Pod instead of assuming the Collector image contains `ls`:

    ```shell
    NODE_NAME=$(kubectl -n observability get pods \
      -l app=otel-collector,component=node \
      -o jsonpath='{.items[0].spec.nodeName}')
    kubectl debug "node/$NODE_NAME" -i --image=busybox:1.36.1 --profile=general -- \
      ls /host/var/log/pods
    ```

    The node filesystem is mounted at `/host` in the temporary debugger. If the directory is empty, the host path may be different (for example, on Talos or some MicroK8s setups). Delete the completed `node-debugger-*` Pod after the check.

## Further reading

- [Kubernetes monitoring with Helm](kubernetes-monitoring.md): use the supported chart when you do not need to own each Collector resource.
- [Collect more data from Kubernetes](kubernetes-collect-more.md): add application auto-instrumentation, optional diagnostic and network metrics, and additional object state.
- [Reduce Kubernetes monitoring volume](kubernetes-reduce-volume.md): lower collection frequency and omit metrics the Kubernetes page does not require.
- [`k8sclusterreceiver` README](https://github.com/open-telemetry/opentelemetry-collector-contrib/tree/main/receiver/k8sclusterreceiver): full list of metrics, including the ones disabled by default.
- [`kubeletstatsreceiver` README](https://github.com/open-telemetry/opentelemetry-collector-contrib/tree/main/receiver/kubeletstatsreceiver): `auth_type` options, `metric_groups`, and the volume-metric attributes.
- [`k8sobjectsreceiver` README](https://github.com/open-telemetry/opentelemetry-collector-contrib/tree/main/receiver/k8sobjectsreceiver): collecting arbitrary objects beyond Events, and pull vs. watch modes.
- [`k8sattributesprocessor` README](https://github.com/open-telemetry/opentelemetry-collector-contrib/tree/main/processor/k8sattributesprocessor): every extractable attribute and the full `pod_association` syntax.
- [`filelogreceiver` README](https://github.com/open-telemetry/opentelemetry-collector-contrib/tree/main/receiver/filelogreceiver) and the [container operator](https://github.com/open-telemetry/opentelemetry-collector-contrib/blob/main/pkg/stanza/docs/operators/container.md): for advanced log parsing.
- [OpenTelemetry Collector on Kubernetes](https://opentelemetry.io/docs/platforms/kubernetes/collector/components): upstream deployment-pattern reference (sidecar / DaemonSet / Deployment / Gateway).
- [Advanced scrubbing with the OTel Collector](./otel-collector-scrubbing.md): if you need to redact PII before it leaves the cluster.
