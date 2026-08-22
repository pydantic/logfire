# Host & Infrastructure Metrics (OpenTelemetry Collector)

A large share of useful telemetry — host CPU/memory/disk, Kubernetes cluster
state, and metrics from database/queue/cache servers — comes from
**infrastructure**, not application code. The OpenTelemetry Collector collects
these and ships them to Logfire over OTLP, with no changes to your app. Logfire
is a fully compliant OpenTelemetry backend, so it ingests any OTLP the Collector
sends.

Reach for this path whenever the user wants "as much useful data as would be
useful," is monitoring a host/VM/cluster, or wants a database/queue/cache server
watched. App instrumentation alone never produces this data.

> The Collector is optional and is an advanced tool. If the user only wants their
> app's own traces, the language SDKs (covered in the main skill) are enough.

## Send Collector data to Logfire

Point the Collector's OTLP exporter at your Logfire region with a write token.
The token authenticates the same way as any OTLP client:

```yaml
exporters:
  otlphttp/logfire:
    endpoint: 'https://logfire-us.pydantic.dev'   # EU: https://logfire-eu.pydantic.dev
    headers:
      Authorization: 'your-write-token'
```

Create a write token in the Logfire UI (Project Settings → Write tokens). Inject
it via environment variable rather than hardcoding it. Add the exporter to your
metrics (and/or logs/traces) pipelines.

Full setup, topologies, and processors:
https://pydantic.dev/docs/logfire/guides/otel-collector/otel-collector-overview/

## Host metrics → Hosts page

Use the `hostmetrics` receiver. Each host that ships these metrics appears on the
**Hosts** page with CPU, memory, load, disk, and network charts.

```yaml
receivers:
  hostmetrics:
    collection_interval: 30s
    scrapers:
      cpu:
      memory:
      load:
      disk:
      filesystem:
      network:
      process:
service:
  pipelines:
    metrics:
      receivers: [hostmetrics]
      exporters: [otlphttp/logfire]
```

Set `host.name` (and other host resource attributes) so hosts are identified
correctly. Guide:
https://pydantic.dev/docs/logfire/guides/otel-collector/host-monitoring/

**App-only alternative:** if you can't run a Collector but the app process should
report its host's metrics, call `logfire.instrument_system_metrics()` (Python,
needs the `system-metrics` extra). The Collector `hostmetrics` receiver is
preferred for true host coverage because it runs per host, independent of any app.

## Docker containers → Docker page

Use the `docker_stats` receiver, pointed at the Docker socket:

```yaml
receivers:
  docker_stats:
    endpoint: unix:///var/run/docker.sock
    api_version: "1.44"   # quoted string -- a bare float like 1.44 is rejected
```

Modern builds of the receiver auto-negotiate the API version; older builds
default to 1.25, too old for current Docker/OrbStack, so pin a recent version
to avoid API-version errors. The collector needs permission to read the socket:
mount `/var/run/docker.sock` into the container and run it as a user that can
read it (often `user: "0:0"` in Docker Compose) -- call out that Docker socket
access, especially as root, is effectively root-level control of the host
before doing this.

Group containers under the real host by passing the host name in from the
shell and setting it as a resource attribute:

```yaml
# docker-compose.yml
services:
  otel-collector:
    environment:
      OTEL_RESOURCE_ATTRIBUTES: host.name=${HOST_NAME}
```

```bash
HOST_NAME=$(hostname) docker compose up
```

A literal `$(hostname)` inside a Compose value does not expand -- it has to
come in from the shell.

If the collector runs in a container and the Logfire base URL is a
localhost/LAN address (self-hosted or local dev), reach the host via
`host.docker.internal` (add `extra_hosts: ["host.docker.internal:host-gateway"]`
in Compose), not `localhost` -- inside the container, `localhost` is the
collector itself. A public cloud Logfire URL needs no change.

Guide: https://pydantic.dev/docs/logfire/observe/docker/

## Kubernetes → Kubernetes page

Collect cluster state, per-node/per-pod metrics, and the `k8s.*` resource
attributes (`k8s.cluster.name`, `k8s.namespace.name`, `k8s.pod.name`,
`k8s.deployment.name`, ...) that drive the **Kubernetes** page. The recommended
pattern is two Collectors — a Deployment for cluster-level state
(`k8sclusterreceiver`) and a DaemonSet for per-node/pod metrics
(`kubeletstatsreceiver`) — plus the `k8sattributesprocessor` to stamp the same
`k8s.*` attributes onto traces from your applications.

Guide:
https://pydantic.dev/docs/logfire/guides/otel-collector/kubernetes-monitoring/

## Database / queue / cache servers → Metrics & Dashboards

The Collector ships receivers for common infrastructure services. Add the
relevant receiver and its metrics become queryable in the **Metrics** explorer
and available for **dashboard panels** and **alerts**:

| Service | Receiver | Example metric prefix |
|---------|----------|-----------------------|
| PostgreSQL | `postgresql` | `postgresql.*` |
| MySQL | `mysql` | `mysql.*` |
| Redis | `redis` | `redis.*` |
| MongoDB | `mongodb` | `mongodb.*` |
| Kafka | `kafkametrics` | `kafka.*` |
| RabbitMQ | `rabbitmq` | `rabbitmq.*` |
| Nginx | `nginx` | `nginx.*` |
| Apache HTTP | `apache` | `apache.*` |
| Elasticsearch | `elasticsearch` | `elasticsearch.*` |
| Memcached | `memcached` | `memcached.*` |

These receivers live in the OpenTelemetry Collector Contrib distribution. Match
the receiver to the services the project actually depends on (read
`pyproject.toml` / `package.json` / `docker-compose.yml` to detect them), and set
`service.instance.id` on each so per-instance metrics stay distinct.

## Cloud provider metrics → Metrics & Dashboards

- **GCP**: the `googlecloudmonitoring` receiver pulls Cloud Monitoring (formerly
  Stackdriver) metrics — needs a service account with monitoring read
  permissions and an explicit `metrics_list` of metric names to collect.
- **AWS**: the `awsecscontainermetrics` receiver reads ECS task-metadata-endpoint
  metrics directly, no extra IAM beyond the task role. For broader CloudWatch
  metrics (RDS, ALB, and other services not on the ECS metadata endpoint), use
  the `awscloudwatchmetrics` receiver, which ships only in the AWS Distro for
  OpenTelemetry (ADOT) collector image
  (`public.ecr.aws/aws-observability/aws-otel-collector`), not the stock
  Contrib distribution — and needs `cloudwatch:GetMetricData` /
  `GetMetricStatistics` / `ListMetrics` IAM permissions.

Full setup, IAM policies, and example ECS/Cloud Run deployments:
https://pydantic.dev/docs/logfire/guides/cloud-metrics/

## Service & resource metadata

Whatever the source, set resource attributes so data is grouped correctly across
the UI. From the Collector, use the `resource`/`resourcedetection` processors or
`OTEL_RESOURCE_ATTRIBUTES`:

- `service.name`, `service.version`, `deployment.environment`
- `service.instance.id` — per-replica identity (standard dashboards filter on it)
- `host.name` — required for the Hosts page to identify a host

## Verify

After wiring a receiver + the Logfire exporter, restart the Collector and check
that the corresponding page (Hosts / Kubernetes) or the Metrics explorer shows
the new data within a minute or two. If nothing appears: confirm the exporter
endpoint/region and write token, that the receiver is in an active pipeline, and
that resource attributes (`host.name`, `service.name`) are set.
