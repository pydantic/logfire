# OpenTelemetry Collector

The OpenTelemtry Collector is a powerful tool that can be used to collect, process, and export telemetry data from various sources.
It is designed to work with a wide range of data sources and can be easily configured to meet your specific needs.
It can be run in a multitude of topologies, including as a standalone service, as a sidecar in a container, or as an agent on a host.

Although it is very powerful and versatile the Collector is also an advanced tool that is not required to use Logfire.
If you don't need any of the Collectors features it is perfectly reasonable to send data from the Logfire SDK directly to our backend, and this is the default configuration for our SDK.

Use cases for the OpenTelemetry Collector include:

- **Centralized configuration**: keep Logfire credentials in a single place. Configure exporting to multiple backends (e.g. Logfire and audit logging) in a single place. All with the ability to update the configuration without needing to make changes to applications.
- **Data transformation**: transform data before sending it to Logfire. For example, you can use the OpenTelemetry Collector to filter out sensitive information, extract structured data from logs or otherwise modify the data before sending it to Logfire.
- **Data enrichment**: add additional context to your logs before sending them to Logfire. For example, you can use the OpenTelemetry Collector to add information about the host or container where the log was generated.
- **Collecting existing data sources**: the Collector can be used to collect system logs (e.g. Kubernetes logs) or metrics from other formats. For example, you can use it to collect container logs from Kubernetes and scrape Prometheus metrics.

As Logfire is a fully compliant OpenTelemetry SDK and backend it does not require any special configuration to be used with the OpenTelemetry collector.
Below we include a couple of examples for using the OpenTelemetry collector, assuming the deployment is being done on Kubernetes, but you can deploy the collector in any system, see the [official documentation](https://opentelemetry.io/docs/collector/deployment/) for more information.

This documentation does not attempt to be a complete guide to the OpenTelemetry collector, but rather a gentle introduction along with some key examples.
For more information on the collector please see the [official documentation](https://opentelemetry.io/docs/collector/).

## Collecting system logs

This example shows how you can use the OpenTelemetry collector to collect systems logs (logs on stdoutt/stderr) from Kubernetes and send them to Logfire.
This may be useful as part of a migration to Logfire if you aren't able to immediately edit all of the applications to install the Logfire SDK, although the data you receive won't be as rich as it would be from tracing with the Logfire SDK.

This relatively simple example is enough in many cases to replace existing systems like ElasticSearch, Loki or Splunk.

To follow this guide you'll need to have a local Kubernetes cluster running.
There are many options for this including [Docker Desktop](https://www.docker.com/blog/how-to-set-up-a-kubernetes-cluster-on-docker-desktop/), [Rancher Desktop](https://docs.rancherdesktop.io/), [Minikube](https://minikube.sigs.k8s.io/docs/start/?arch=%2Fmacos%2Farm64%2Fstable%2Fbinary+download), [Kind](https://kind.sigs.k8s.io/), [k3s](https://docs.k3s.io/quick-start).

We'll first create an application via `apps.yaml` that emits some structured and unstructured logs to stdout/stderr:

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

Deploy this application via `kubectl apply -f apps.yaml`.

Now we will set up a collector that can scrape logs from these apps, process them and send them to logfire.

We'll need to store Logfire credentials somewhere, a Kubernetes Secret is a reasonable choice, a better choice for a production environment would be to use [External Secrets Operator](https://external-secrets.io/latest/).

First create a Logfire write token, see [Create Write Tokens](./create-write-tokens.md).

Now to save it as a secret in Kubernetes run the following command, replacing `your-write-token` with the value of the write token you just created:

```shell
kubectl create secret generic logfire-token --from-literal=logfire-token=your-write-token
```

Note that this is equivalent to the following `secrets.yaml` file, but using `kubectl` is easier because it will base64 encode the secret for you.

```yaml title="secrets.yaml"
apiVersion: v1
kind: Secret
metadata:
  name: logfire-token
type: Opaque
data:
  logfire-token: base64-encoded-logfire-token
```

For the OTel Collector to scrape logs it will need permissions into the Kubernetes API which Kubernetes does not give out by default (you wouldn't want random pods being able to see logs from other pods by default!).

To do this we'll create an `rbac.yaml` file with the following content:

```yaml title="rbac.yaml"
apiVersion: v1
kind: ServiceAccount
metadata:
  name: otel-collector
  namespace: default
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: otel-collector-role
rules:
- apiGroups: [""]
  resources: ["pods", "namespaces"]
  verbs: ["get", "list", "watch"]
- apiGroups: ["apps"]
  resources: ["replicasets"]
  verbs: ["get", "list", "watch"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: otel-collector-rolebinding
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: otel-collector-role
subjects:
- kind: ServiceAccount
  name: otel-collector
  namespace: default
```

Apply this configuration via `kubectl apply -f rbac.yaml`.

Now we can create the deployment for the collector itself.
There are several options for deploying the OTel collector, including:

- As a sidecar container on each / some pods. This requires less permissions but implies manual configuration of each deployment with a sidecar. This option may work well if you want to bolt on **Logfire** to specific existing applications you control without modifying the application itself or deploying the collector cluster wide.
- As a DaemonSet, this will deploy the collector on every node in the cluster. This is a good option if you want to collect logs from all pods in the cluster without modifying each deployment. Additionally DaemonSets can collect certain information that is not available to sidecars or services. This is the option we will use in this guide.
- As a Service/Gateway, this option that allows you to deploy the collector as a standalone Kubernetes service.

Create a `collector.yaml` file with the following content:

```yaml title="collector.yaml"
apiVersion: v1
kind: ConfigMap
metadata:
  name: otel-collector-config
data:
  config.yaml: |-
    receivers:
      filelog:
        include_file_path: true
        include:
          - /var/log/pods/*/*/*.log
        exclude:
          # Exclude logs from all containers named otel-collector
          - /var/log/pods/*/otel-collector/*.log
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
    exporters:
      debug:
      otlphttp:
        endpoint: "https://logfire-api.pydantic.info"
        headers:
          Authorization: "Bearer ${env:LOGFIRE_TOKEN}"
    service:
      pipelines:
        logs:
          receivers: [filelog]
          exporters: [debug, otlphttp]
---
apiVersion: apps/v1
kind: DaemonSet
metadata:
  name: otel-collector
  labels:
    app: opentelemetry
    component: otel-collector
spec:
  selector:
    matchLabels:
      app: opentelemetry
      component: otel-collector
  template:
    metadata:
      labels:
        app: opentelemetry
        component: otel-collector
    spec:
      serviceAccountName: otel-collector
      terminationGracePeriodSeconds: 1
      containers:
      - name: otel-collector
        image: otel/opentelemetry-collector-contrib:0.119.0
        env:
        - name: LOGFIRE_TOKEN
          valueFrom:
            secretKeyRef:
              name: logfire-token
              key: logfire-token
        resources:
          limits:
            cpu: 100m
            memory: 200Mi
          requests:
            cpu: 100m
            memory: 200Mi
        volumeMounts:
        - mountPath: /var/log
          name: varlog
          readOnly: true
        - mountPath: /var/lib/docker/containers
          name: varlibdockercontainers
          readOnly: true
        - mountPath: /etc/otelcol-contrib/config.yaml
          name: data
          subPath: config.yaml
          readOnly: true
      volumes:
      - name: varlog
        hostPath:
          path: /var/log
      - name: varlibdockercontainers
        hostPath:
          path: /var/lib/docker/containers
      - name: data
        configMap:
          name: otel-collector-config
```

Apply this configuration via `kubectl apply -f otel-collector.yaml`.

You should now see logs from the `plain-app` and `json-app` in your Logfire dashboard!
