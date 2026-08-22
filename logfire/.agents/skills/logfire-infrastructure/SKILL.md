---
name: logfire-infrastructure
description: Monitor hosts, Docker containers, Kubernetes clusters, database/queue/cache servers, and cloud-provider metrics with Pydantic Logfire — no application code required. Use this skill whenever the user asks to "monitor my host/server/VM", "monitor my Docker containers", "monitor my Kubernetes cluster", "send infrastructure metrics to Logfire", "watch my database/Postgres/Redis/MongoDB/Kafka", "collect cloud metrics" (AWS/GCP), or mentions the OpenTelemetry Collector in the context of Logfire. This is infrastructure only — for instrumenting APPLICATION CODE (traces, logs, AI/agent spans) use the logfire-instrumentation skill instead.
---

# Monitor Infrastructure with Logfire

## When to Use This Skill

Invoke this skill when:
- User asks to monitor a host, server, VM, container, or Kubernetes cluster
- User names infrastructure by product — Docker, Kubernetes, Postgres, Redis, MongoDB, Kafka, RabbitMQ, Nginx, Apache, Elasticsearch, Memcached — rather than application code
- User wants cloud-provider metrics (GCP Cloud Monitoring, AWS CloudWatch/ECS)
- User asks to "get me set up properly" or "send as much data as would be useful" and infrastructure hasn't been covered yet
- User mentions the OpenTelemetry Collector

Do **not** use this skill for application-level traces, logs, or AI/agent spans — that's `logfire-instrumentation`. The two compose: a full setup often runs both.

## How This Works

The OpenTelemetry Collector ships host, container, cluster, and infrastructure-service metrics to Logfire with **no application code changes** — Logfire ingests any OTLP, so the Collector is the entire mechanism. This is optional and is an advanced tool: if the user only wants their app's own traces, `logfire-instrumentation`'s language SDKs are enough on their own.

## Step 1: Identify What to Monitor

Detect the infrastructure actually in play, don't assume:

- **Host/VM**: monitoring the machine itself (CPU, memory, disk, network, load).
- **Docker**: read `docker-compose.yml` / `Dockerfile`s for running containers.
- **Kubernetes**: look for manifests, a `kubeconfig`, or `kubectl` context.
- **Database/queue/cache servers**: read `docker-compose.yml` / `pyproject.toml` / `package.json` for Postgres, MySQL, Redis, MongoDB, Kafka, RabbitMQ, Nginx, Apache, Elasticsearch, or Memcached.
- **Cloud provider**: GCP or AWS metrics (Cloud Monitoring, CloudWatch, ECS), when the user names the provider or the app clearly runs there.

More than one can apply at once — a single Collector can run multiple receivers in parallel pipelines.

## Step 2: Authenticate and Select the Exact Project

Skip this if `.logfire` credentials or `LOGFIRE_TOKEN` already resolve to the right project and region (check with `logfire whoami` first). Otherwise, run the CLI yourself from the application directory, prefixed with `uvx` or `npx` (whichever is available) — it's a setup tool, not an app dependency:

```bash
logfire auth
logfire projects list
logfire projects use <project-name>
logfire whoami
```

- Determine the target region (US or EU) from the project's URL or the user's context *before* authenticating. The `--region` flag is global and goes right after `logfire`, not after the subcommand: `logfire --region eu auth`. Omit it and let `auth` ask if the region is unknown — it completes without a TTY either way.
- `auth` opens a browser to sign in or create a free account.
- `projects list`: if exactly one project is available, use it. Several plausible and none identified? Ask. None exist? `logfire projects new <project-name>` instead. Need a specific org? Add `--org <organization-name>` to `projects use`.
- `whoami`'s org/project/region is what every later step — the Collector's write token, verification, any link you give the user — must match. Never substitute a different or "latest" project.
- A write token for the Collector's exporter comes from Project Settings → Write tokens in the Logfire UI, not from this CLI flow. Never print, log, hard-code, commit, or echo it — inject it via environment variable and check only that it's set, not its value.

## Step 3: Configure the Collector

Follow the [collector reference](./references/collector/host-and-infra-metrics.md) for the receiver(s) identified in Step 1 — it covers the shared exporter setup, then a dedicated section per source: host metrics, Docker, Kubernetes, database/queue/cache servers, and cloud-provider metrics, each with the exact receiver name, a working config, and the caveats that actually bite (Docker socket permissions, API version pinning, `host.docker.internal` vs `localhost`, IAM permissions, ADOT vs. Contrib collector images).

Set the same service & resource metadata conventions the [collector reference](./references/collector/host-and-infra-metrics.md) describes — `host.name`, `service.name`, `service.instance.id` — so data groups correctly across the Hosts, Kubernetes, and Metrics pages.

## Step 4: Verify

Wiring a receiver isn't done when the Collector starts cleanly — confirm the data actually reached the right page for the right host/container/cluster, not just that something arrived:

1. **Restart the Collector** after any config change.
2. **Check the specific product page** — Hosts, Docker, or Kubernetes — or the Metrics explorer for database/queue/cache/cloud sources. Look for the *exact* host/container/cluster you configured, not just that the page has data at all.
3. **If nothing appears**, check in order: the exporter endpoint/region and write token, that the receiver is in an active pipeline, and that resource attributes (`host.name`, `service.name`) are set — the [reference's own Verify section](./references/collector/host-and-infra-metrics.md) has the full troubleshooting path.
4. **Fix and re-check** until the specific source is visible, not just "some" data.

## References

- [Host, Docker, Kubernetes, database/queue/cache, and cloud-provider metrics via the OTel Collector](./references/collector/host-and-infra-metrics.md) — receiver configs, IAM/permission caveats, and its own verify loop.
