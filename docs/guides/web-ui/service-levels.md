---
title: "Service Levels: SLOs, reliability targets, and burn-rate alerts"
description: "Set a reliability target — a Service Level Objective (SLO) — for a service, for example 99.9% of requests succeed over 30 days, and let Logfire track the error budget and page you before you miss it."
---
# Service Levels

A **reliability target** — Logfire's name for a **Service Level Objective (SLO)**, the industry-standard way to set a measurable reliability goal — is a promise about a service, written as a percentage over a time window: *"99.9% of requests succeed over the last 30 days."* In Logfire you set one on a service, and Logfire watches the service and **pages you when it's heading toward missing the promise, well before users notice.** (An SLO is your *internal* target; a Service Level Agreement, or SLA, is the external contract with financial consequences — Logfire tracks SLOs.)

The <OpenInLogfire path="service-levels" variant="inline" label="Service Levels" /> page lists every reliability target across the project. Each target lives on its service, under the service's **Reliability** tab.

!!! note "Plans and limits"
    Reliability targets are a **Growth** feature (also available on Enterprise and self-hosted). The number of targets per organization depends on your plan.

## What a reliability target is made of

When you create a target you answer three questions:

- **What counts as a "good" request, and out of which requests?** Logfire measures a fraction — good events divided by total events. This ratio is the service's **Service Level Indicator (SLI)**, the signal the SLO is measured against. You define both parts with a boolean SQL condition: *"What counts as a failure?"* and *"Out of which set of events?"*
- **What's the target?** A percentage — presets run from **99.0%** to **99.99%** (default **99.9%**).
- **Over what window?** A **rolling window** — the trailing period the percentage is measured over. Presets are **1, 7, 28, 30, and 90 days** (default 30). Your plan caps the maximum window.

Two derived ideas do the heavy lifting:

- **Error budget** — the small fraction of failures the target *allows*. A 99.9% target over 30 days budgets 0.1% of events to fail; the target's detail page shows **"Error budget remaining."**
- **Burn rate** — how fast you're spending that budget right now. Burning at 1× exactly uses the budget over the window; 14.4× would exhaust a 30-day budget in about two days.

## Create a reliability target

1. Open a service, go to its **Reliability** tab, and click **New target**.
2. Pick a template — the card you choose sets what "good" means:
    - **Availability** — good = requests that didn't error.
    - **Latency** — good = requests under a **Max duration (seconds)** you set.
    - **AI quality** — a *quality* SLI (the SLI dimension that sits alongside availability and latency): good = requests whose evaluation score clears a **Minimum eval score** (reads `gen_ai.evaluation.score.value`, populated by [pydantic-evals](../../evaluate/overview.md)).
3. Fill in the wizard: name it, confirm the good/total conditions, and choose **where the data comes from** — **Events** (one row per request, RPC, or job — most targets use this) or **Metrics** (sum a counter or gauge you already record). Both are **count-based** SLIs (good ÷ total), the request-based style the SRE literature recommends; Logfire doesn't use time-based/uptime SLIs. Optionally scope to specific deployment **environments**.
4. Set the **Target (%)** and **Rolling window**. A **live preview** backtests the target against your recent data so you can see the success rate and burn before you commit.
5. Optionally choose notification channels for the alerts Logfire is about to generate, then click **Create target**.

## Burn-rate alerts, created for you

Every target automatically generates **three burn-rate alerts**, so you don't hand-write alert SQL:

| Tier | Reacts to | Fires at | Severity |
|------|-----------|----------|----------|
| **Fast burn** | a sudden outage (1h / 5m windows) | 14.4× budget burn | pages you |
| **Medium burn** | a steady problem (6h / 30m) | 6× burn | pages you |
| **Slow burn** | a slow leak (3d / 6h) | 1× burn | opens a ticket |

These three tiers follow the [Google SRE Workbook's **multiwindow, multi-burn-rate** method](https://sre.google/workbook/alerting-on-slos/): each checks **two windows at once** so a brief blip doesn't page you but a real regression does. Route each alert to a channel from the target's detail page — see [Alerts](alerts.md) for channels and notifications. Tiers that can't structurally fire for a low target are skipped.

## Track a target

The target's detail page shows three cards — **Current service level**, **Target**, and **Error budget remaining** — a **burn-rate chart** for the last 7 days, the state of its three burn-rate alerts, and a **How it's measured** panel with the exact good/total queries. When a target is breached, **Investigate failing events** jumps to the matching events in the [Live view](live.md).

## Reliability targets for LLM providers

If a service calls an LLM, you can install ready-made **availability targets** for the providers it uses in one step — **LLM providers** on the Reliability tab (or the reliability chips on the [LLMs and Providers](llms.md) page). Logfire ships presets for **OpenAI**, **Anthropic**, **Google (Gemini / Vertex)**, and a catch-all **Any LLM provider**, each defaulting to **99% over 28 days**, counting only server-side failures (5xx, rate limits, timeouts) as bad.

## Next steps

- [Alerts](alerts.md) — route the generated burn-rate alerts and add your own.
- [Detect Service is Down](../../how-to-guides/detect-service-is-down.md) — a lighter-weight uptime check.
- [Services](services.md) — where reliability targets are created and reviewed.
