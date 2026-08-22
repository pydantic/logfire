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

Check first, before assuming anything needs to happen:

```bash
logfire --non-interactive whoami
```

If that already reports the right project and region, skip to Step 3. Otherwise, run the CLI yourself from the application directory, prefixed with `uvx` or `npx` (whichever is available) — it's a setup tool, not an app dependency. **Always put `--non-interactive` immediately after `logfire`, on every invocation.** Without it, a question with nobody to answer it (which org? which project?) blocks on a read that never returns — there is no TTY for the CLI to notice is missing, so it cannot detect this on its own; the flag is the only way to guarantee a clear error instead of a silent hang.

```bash
logfire --non-interactive --region eu auth
logfire --non-interactive projects list --json
logfire --non-interactive projects use <project-name> --org <organization-name>
logfire --non-interactive whoami
```

- Determine the target region (US or EU) from the project's URL or the user's context *before* authenticating, and pass it up front: `--region {us,eu}` is global and goes right after `logfire --non-interactive`, before the subcommand. Don't rely on `auth` asking when it's omitted.
- `auth` does **not** open a browser itself when there's no TTY, which an agent's own environment never has — it prints a URL and polls for you to finish. Relay that URL to the user; don't wait silently.
- `projects list --json`: if exactly one project is returned, use it. Several plausible and none identified? Ask the user. None exist? `logfire --non-interactive projects new <project-name> --org <organization-name>` instead.
- If any command fails with `NonInteractiveError`, its message names the exact missing flag (commonly `--org`). Supply it and retry once — don't drop `--non-interactive` to make the error go away.
- `whoami`'s org/project/region is what every later step — the Collector's write token, verification, any link you give the user — must match. Never substitute a different or "latest" project.
- A write token for the Collector's exporter comes from **Project Settings → Write tokens** in the Logfire UI, not from this CLI flow — the CLI's own credentials authenticate you as a person, not the Collector as a data source. Never print, log, hard-code, commit, or echo the write token — inject it via environment variable and check only that it's set, not its value.

## Step 3: Configure the Collector

Follow the [collector reference](./references/collector/host-and-infra-metrics.md) for the receiver(s) identified in Step 1 — it covers the shared exporter setup, then a dedicated section per source: host metrics, Docker, Kubernetes, database/queue/cache servers, and cloud-provider metrics, each with the exact receiver name, a working config, and the caveats that actually bite (Docker socket permissions, API version pinning, `host.docker.internal` vs `localhost`, IAM permissions, ADOT vs. Contrib collector images).

Set the same service & resource metadata conventions the [collector reference](./references/collector/host-and-infra-metrics.md) describes — `host.name`, `service.name`, `service.instance.id` — so data groups correctly across the Hosts, Kubernetes, and Metrics pages.

Before starting or restarting the Collector, validate the config file — a receiver typo or bad indentation should surface as a validation error, not a Collector that starts, logs nothing useful, and silently drops the pipeline:

```bash
otelcol-contrib validate --config=collector-config.yaml
# or, for the core (non-Contrib) distribution: otelcol validate --config=...
```

If neither binary is on `PATH`, find the actual binary name from how the Collector is deployed (the container image's entrypoint, the systemd unit, the Helm chart's `command:`) rather than guessing — `docker compose config` or `kubectl get pod <name> -o yaml` will show it.

## Step 4: Verify

Wiring a receiver isn't done when the Collector starts cleanly — confirm the data actually reached the right page for the right host/container/cluster, not just that something arrived. **Never report a metric as "arrived" without having queried for it in this same session** — a plausible-sounding summary that wasn't checked is worse than saying you couldn't verify.

1. **Restart the Collector** after any config change (having validated it, above).
2. **Query for the exact resource you configured, not just any data on the page.** If a Logfire MCP server or API is connected in this session, query for the specific `host.name` / container / cluster you set in Step 3 within the last few minutes — a query that returns zero rows for that exact identifier means it didn't land, even if the page shows data from something else. Otherwise, open the specific product page — **Hosts**, **Docker**, or **Kubernetes** — or the **Metrics** explorer for database/queue/cache/cloud sources, and look for that same exact identifier.
3. **If nothing appears**, check in order: the exporter endpoint/region and write token, that the receiver is in an active pipeline (not defined but never referenced under `service.pipelines`), and that resource attributes (`host.name`, `service.name`) are set — the [reference's own Verify section](./references/collector/host-and-infra-metrics.md) has the full troubleshooting path.
4. **Fix and re-check** until the specific source is visible, not just "some" data.

Close with a final report built from what you just confirmed — org/project/region from `whoami`, which receiver(s) are active, and the exact host/container/cluster identifier you verified — not a template. A report with a placeholder in it means a step above was skipped, not finished.

## References

- [Host, Docker, Kubernetes, database/queue/cache, and cloud-provider metrics via the OTel Collector](./references/collector/host-and-infra-metrics.md) — receiver configs, IAM/permission caveats, and its own verify loop.
