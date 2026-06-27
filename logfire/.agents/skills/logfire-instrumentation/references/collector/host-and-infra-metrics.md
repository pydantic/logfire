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
https://docs.pydantic.dev/logfire/how-to-guides/otel-collector/otel-collector-overview/

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
https://docs.pydantic.dev/logfire/how-to-guides/otel-collector/host-monitoring/

**App-only alternative:** if you can't run a Collector but the app process should
report its host's metrics, call `logfire.instrument_system_metrics()` (Python,
needs the `system-metrics` extra). The Collector `hostmetrics` receiver is
preferred for true host coverage because it runs per host, independent of any app.

## Kubernetes → Kubernetes page

Collect cluster state, per-node/per-pod metrics, and the `k8s.*` resource
attributes (`k8s.cluster.name`, `k8s.namespace.name`, `k8s.pod.name`,
`k8s.deployment.name`, ...) that drive the **Kubernetes** page. The recommended
pattern is two Collectors — a Deployment for cluster-level state
(`k8sclusterreceiver`) and a DaemonSet for per-node/pod metrics
(`kubeletstatsreceiver`) — plus the `k8sattributesprocessor` to stamp the same
`k8s.*` attributes onto traces from your applications.

Guide:
https://docs.pydantic.dev/logfire/how-to-guides/otel-collector/kubernetes-monitoring/

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
