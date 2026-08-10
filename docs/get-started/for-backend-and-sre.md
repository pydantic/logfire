---
title: "For backend engineers and SREs"
description: "A starting path for engineers who run services: instrument your app, watch requests live, find the service that's misbehaving, and build the dashboards and alerts that catch problems early."
---

# For backend engineers and SREs

You run services and you want to know, fast, when one is slow or failing. This path takes you from your first instrumented request to watching traffic live, then to the dashboards and alerts that tell you about a problem before your users do. (SRE stands for site reliability engineer, the person who keeps production healthy.)

Follow these in order. Each link says why it's here.

## Your path

1. **[Send your first trace to Logfire](../first-trace.md)**: install Logfire and link this machine to a project. A **trace** is the full record of one request or job; a **span** is one step inside it (a database query, an outgoing API call). This is the five-minute foundation everything else builds on.

2. **Instrument your framework and dependencies**: one line each turns on tracing for the request path:
    - Web frameworks: [FastAPI](../integrations/web-frameworks/fastapi.md), [Django](../integrations/web-frameworks/django.md), [Flask](../integrations/web-frameworks/flask.md), [Starlette](../integrations/web-frameworks/starlette.md) (see [all web frameworks](../integrations/web-frameworks/index.md))
    - Databases: [PostgreSQL (psycopg)](../integrations/databases/psycopg.md), [SQLAlchemy](../integrations/databases/sqlalchemy.md), [Redis](../integrations/databases/redis.md), [asyncpg](../integrations/databases/asyncpg.md)

3. **[Watch your app's traces arrive live](../guides/web-ui/live.md)**: tail requests as they happen while you reproduce a bug or watch a deploy. You can search history in SQL from the same screen.

4. **[Find which service is slow or failing](../guides/web-ui/services.md)**: see every service ranked by request rate, error rate, and latency, then drill into the failing traces. This view also gives you per-service health at a glance. (It's in Beta.)

5. **[Explore: ask anything of your data in SQL](../guides/web-ui/explore.md)**: write SQL over your traces and metrics to answer one-off questions: which endpoint is slowest, which requests errored, where the time went.

6. **[Dashboards](../guides/web-ui/dashboards.md)**: turn the questions you check often into charts on one screen: is latency creeping up, are errors spiking during this rollout.

7. **[Alerts](../guides/web-ui/alerts.md)**: an alert is a SQL query Logfire runs on a schedule; when it returns rows, Logfire notifies you in Slack, Opsgenie, or a webhook, so you hear about trouble without watching a screen.

8. **[Set reliability targets (Service Levels)](../guides/web-ui/service-levels.md)**: define a target like "99.9% of requests succeed over 30 days" and Logfire tracks the error budget and auto-generates burn-rate alerts that page you before you miss it.

!!! note "Service Levels are a Growth feature"
    Reliability targets (Service Levels) are available on the Growth plan and above (also Enterprise and self-hosted). On any plan, the [Services view](../guides/web-ui/services.md) gives per-service health (request rate, error rate, latency) and [Alerts](../guides/web-ui/alerts.md) tell you when a threshold is crossed.

## Try the full journey

- **[Debug a slow endpoint](../cookbook/debug-a-slow-endpoint.md)**: a start-to-finish walkthrough: find the slow request in the Live view, open its trace, and see exactly which step ate the time.
