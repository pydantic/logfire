---
title: "Set reliability targets for services and large language model providers"
description: "Define measurable reliability goals, track error budgets and burn rates, and investigate the events that put a target at risk."
---
# Service Levels

Set a measurable reliability goal for a service or large language model (LLM) provider, then watch its error budget and burn rate before the target is missed.

A service level objective (SLO) is a target for how reliable a service should be, such as "99.9% of checkout requests succeed over the last 30 days." Logfire calls each SLO a **reliability target**. An SLO is an internal engineering target; a service level agreement (SLA) is an external contract.

You'll find <OpenInLogfire path="service-levels" variant="inline" label="Service levels" /> under **Notify** in the project sidebar. The page lists every target in the project. Search by target name, service, provider, or description; filter by status; or group by service, status, time window, source, or not at all. Service detail pages show the same targets on their **Reliability** page.

!!! note "Plans and limits"
    Reliability targets are available on **Growth**, **Enterprise**, and self-hosted Logfire. Growth organizations can create up to five targets across the organization and use windows up to 30 days. Enterprise and self-hosted organizations have no target-count limit and can use windows up to 90 days. Project retention still limits the available history.

## Choose what good looks like

A target combines:

1. The total events or values to measure.
2. The subset that counts as bad.
3. The percentage that should be good over a rolling time window.

The resulting good-event ratio is the service level indicator (SLI). Percentage presets range from **99%** to **99.99%**, with **99.9%** as the default. Window presets are **1, 7, 28, 30, and 90 days**.

Two derived values show whether the goal is at risk:

- **Error budget** is the amount of unreliability the target allows. A 99.9% target allows 0.1% of included events to be bad.
- **Burn rate** is how quickly the service is spending that budget. At 1x, one complete budget would be consumed over the target's rolling window.

## Start from a template

From a service detail page, select **Reliability**, then **New target** and choose:

- **Availability** for records that did not error.
- **Latency** for records below a duration threshold.
- **AI / LLM calls** for calls without a provider-side failure.
- **AI quality (eval score)** for records that reach an evaluation threshold. An evaluation (eval) is a repeatable test of model or agent behavior. This template uses `gen_ai.evaluation.score.value`, which [Pydantic Evals](../../evaluate/overview.md) can populate.
- **Custom SQL**, using Structured Query Language conditions, when the preset conditions do not fit.

## Choose records or metrics

**Records** measure rows such as requests, remote procedure calls (RPCs), background jobs, and LLM calls. Define the total population and bad subset with SQL boolean conditions. The setup wizard previews matching records before you save.

**Metrics** measure a count or other additive value, a gauge fraction, a cumulative counter, or values below a histogram latency threshold. Their burn-rate history appears after you save the target.

You can restrict either source to selected deployment environments. Set the target percentage and window, then choose notification channels for its generated alerts.

## Let Logfire watch the burn rate

Each target generates up to three alerts:

| Tier | Windows | Threshold | Severity |
|------|---------|-----------|----------|
| **Fast burn** | 1 hour and 5 minutes | 14.4x | page |
| **Medium burn** | 6 hours and 30 minutes | 6x | page |
| **Slow burn** | 3 days and 6 hours | 1x | ticket |

These tiers follow the multiwindow, multi-burn-rate method in the [Google Site Reliability Engineering (SRE) Workbook](https://sre.google/workbook/alerting-on-slos/). Checking two windows keeps a brief spike from firing an alert meant for a sustained regression. Logfire omits a tier when the target is too low for that tier to fire meaningfully.

Route alerts from the target detail page. See [Alerts](alerts.md) for notification-channel setup.

## Track the budget and investigate failures

The target detail page shows **Current service level**, **Target**, and **Error budget remaining**. **Reliability history** defaults to hourly error-budget history for the last 24 hours; switch to **Burn rate** and choose a time span to inspect budget consumption.

The **How it's measured** panel records the scope and exact conditions. Select **Investigate failing events** to open the matching records in [Explore](explore.md).

## Monitor an LLM provider

On the **Providers** tab of [LLMs and Providers](llms.md), select **Set reliability targets** for an observed provider. Choose an availability or latency target for that provider across every service that calls it. To limit an LLM target to one service, create it from that service's **Reliability** page instead.

Provider targets default to **99% over 28 days**. Availability targets treat server failures, rate limits, timeouts, and connection errors as bad. Recognized OpenAI and Anthropic client errors, such as invalid requests or credentials, are excluded because they do not measure provider availability.
