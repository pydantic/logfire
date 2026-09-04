---
name: logfire-infrastructure
description: Monitor hosts, Docker containers, Kubernetes clusters, database/queue/cache servers, and cloud-provider metrics with Pydantic Logfire — no application code required. Use this skill whenever the user asks to "monitor my host/server/VM", "monitor my Docker containers", "monitor my Kubernetes cluster", "send infrastructure metrics to Logfire", "watch my database/Postgres/Redis/MongoDB/Kafka", "collect cloud metrics" (AWS/GCP), or mentions the OpenTelemetry Collector in the context of Logfire. This is infrastructure only — for instrumenting APPLICATION CODE (traces, logs, AI/agent spans) use the logfire-instrumentation skill instead.
---

# Monitor Infrastructure with Logfire

Do **not** use this skill for application-level traces, logs, or AI/agent spans — that's `logfire-instrumentation`. The two compose: a full setup often runs both.

## How This Works

The OpenTelemetry Collector ships host, container, cluster, and infrastructure-service metrics to Logfire with **no application code changes** — Logfire is a fully compliant OTel backend and ingests standard OTLP traces, logs, and metrics from it (one narrow exception noted in the [collector reference](./references/collector/host-and-infra-metrics.md)), so the Collector is the entire mechanism. This is optional and is an advanced tool: if the user only wants their app's own traces, `logfire-instrumentation`'s language SDKs are enough on their own.

## Step 1: Authenticate and Select the Exact Project

Do not open, read, or run any infrastructure config file (`docker-compose.yml`, a Kubernetes manifest, or similar) until `whoami` confirms you're authenticated to the right project — nothing about this step requires knowing what's being monitored. Auth is also the one step that can block on a human (browser sign-in), so starting it first means that wait begins on turn one, not after Step 2's detection work.

Check first — `uvx logfire --non-interactive whoami` (JS: `npx logfire whoami`) — and skip to Step 2 if it already reports the right project and region. Otherwise, full command sequence, flags, and gotchas (the `--non-interactive` requirement, why `auth` won't open a browser for you, the `LOGFIRE_TOKEN`-vs-credentials-file conflict) plus where the Collector's own write token comes from: [Authenticate and Select the Exact Project](../logfire-instrumentation/references/auth.md).

## Step 2: Identify What to Monitor

Detect the infrastructure actually in play, don't assume:

- **Host/VM**: monitoring the machine itself (CPU, memory, disk, network, load).
- **Docker**: read `docker-compose.yml` / `Dockerfile`s for running containers.
- **Kubernetes**: look for manifests, a `kubeconfig`, or `kubectl` context.
- **Database/queue/cache servers**: read `docker-compose.yml` / `pyproject.toml` / `package.json` for Postgres, MySQL, Redis, MongoDB, Kafka, RabbitMQ, Nginx, Apache, Elasticsearch, or Memcached.
- **Cloud provider**: GCP or AWS metrics (Cloud Monitoring, CloudWatch, ECS), when the user names the provider or the app clearly runs there.

More than one can apply at once — a single Collector can run multiple receivers in parallel pipelines.

## Step 3: Configure the Collector

Follow the [collector reference](./references/collector/host-and-infra-metrics.md) for the receiver(s) identified in Step 2 — it covers the shared exporter setup, then a dedicated section per source: host metrics, Docker, Kubernetes, database/queue/cache servers, and cloud-provider metrics, each with the exact receiver name, a working config, and the caveats that actually bite (Docker socket permissions, API version pinning, `host.docker.internal` vs `localhost`, IAM permissions, ADOT vs. Contrib collector images).

Set the same service & resource metadata conventions the [collector reference](./references/collector/host-and-infra-metrics.md) describes — `host.name`, `service.name`, `service.instance.id` — so data groups correctly across the Hosts, Kubernetes, and Metrics pages.

Before starting or restarting the Collector, validate the config file — a receiver typo or bad indentation should surface as a validation error, not a Collector that starts, logs nothing useful, and silently drops the pipeline:

```bash
otelcol-contrib validate --config=collector-config.yaml
# or, for the core (non-Contrib) distribution: otelcol validate --config=...
```

If neither binary is on `PATH`, inspect the running Collector container (for example with `kubectl exec`) or use the deployment-specific validation command from the image entrypoint, systemd unit, or Helm chart. `docker compose config` or `kubectl get pod <name> -o yaml` can show the command when it is explicitly configured.

## Step 4: Verify

Wiring a receiver isn't done when the Collector starts cleanly — confirm the data actually reached the right page for the right host/container/cluster, not just that something arrived. **Never report a metric as "arrived" without having queried for it in this same session** — a plausible-sounding summary that wasn't checked is worse than saying you couldn't verify.

1. **Restart the Collector** after any config change (having validated it, above).
2. **Query for the exact resource you configured, not just any data on the page.** If a Logfire MCP server or API is connected in this session, query for the specific `host.name` / container / cluster you set in Step 3 within the last few minutes — a query that returns zero rows for that exact identifier means it didn't land, even if the page shows data from something else. Otherwise, open the specific product page — **Hosts**, **Docker**, or **Kubernetes** — or the **Metrics** explorer for database/queue/cache/cloud sources, and look for that same exact identifier.
3. **If nothing appears**, check in order: the exporter endpoint/region and write token, that the receiver is in an active pipeline (not defined but never referenced under `service.pipelines`), and that resource attributes (`host.name`, `service.name`) are set — the [reference's own Verify section](./references/collector/host-and-infra-metrics.md) has the full troubleshooting path.
4. **Fix and re-check** until the specific source is visible, not just "some" data.

Close with a final report built from what you just confirmed — org/project/region from `whoami`, which receiver(s) are active, and the exact host/container/cluster identifier you verified — not a template. **Include a direct link to the relevant view** (`/hosts`, `/docker`, `/kubernetes`, or `/metrics`, based on the source) using the project's URL from `whoami`, so the user can see their own source arrive without having to ask where to look. A report with a placeholder in it means a step above was skipped, not finished.

## References

- [Host, Docker, Kubernetes, database/queue/cache, and cloud-provider metrics via the OTel Collector](./references/collector/host-and-infra-metrics.md) — receiver configs, IAM/permission caveats, and its own verify loop.
