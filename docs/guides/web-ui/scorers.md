---
title: "Logfire Scorers: platform-run LLM-judge evaluations for live agent runs"
description: "Turn on a platform-run LLM-as-judge for one of your agents from the Scorers tab in Pydantic Logfire. Continuously score live agent runs against a rubric you write — no evaluator code and no judge API key of your own."
---
# Scorers

!!! note "Preview — limits subject to change"
    Hosted scorers are in preview and free while we gather feedback, with limits that may change before general availability (see [Quota and cost](#quota-and-cost)). Tell us what's missing or broken in the [Logfire Slack community](https://pydantic.dev/docs/logfire/join-slack/) or email [support@pydantic.dev](mailto:support@pydantic.dev).

**Scorers** are LLM-as-judge evaluators that *the platform runs for you* over your live agent runs. You write a rubric in the Logfire web UI, and Logfire continuously judges matching runs server-side and writes the scores back into your project — so a quality signal on production traffic shows up in the [Live Evaluations](live-evals.md) page with no evaluator code in your own application and no judge API key of your own to manage.

This is the counterpart to Pydantic AI's [online evaluation](https://pydantic.dev/docs/ai/evals/online-evaluation/), where you wire up evaluators in your own service. A scorer needs neither: point it at an agent, describe what "good" looks like, and Logfire does the judging.

During the preview a scorer targets **one agent** (any agent whose runs already show up on your **Agents** page) and uses an **LLM-judge rubric**. Broader targeting and other scorer types are on the way.

## How scorers work

Each enabled scorer runs a loop on the platform:

1. **Select** — Logfire picks up new runs of the target agent as they arrive (windowed on ingestion time; it doesn't backfill runs from before you enabled the scorer).
2. **Judge** — a bundled judge model reads each run against your rubric and produces a `0`–`1` score plus a short free-text reason.
3. **Write back** — the score is written into your project as a `gen_ai.evaluation.result` OpenTelemetry log event, parented to the run it scored.

Because the write-back is an ordinary evaluation event — the exact shape the SDK emits for online evals — scores land in all the places you already look: the [Live Evaluations](live-evals.md) page, the agent's evaluations, the trace view, and SQL in [Explore](explore.md). See [Viewing scores](#viewing-scores).

## Creating a scorer

Open the **Agents** page from the project sidebar, click the agent you want to score, and select its **Scorers** tab. Create a scorer with:

- **Name** — identifies the scorer within the agent.
- **Rubric** — the judging instructions, written in plain language. For example: `Score how helpful, accurate, and concise the assistant response is for the user request. Higher is better.`
- **Score name** — the evaluator name the scores are recorded under. This is the name you'll see for the scorer on the [Live Evaluations](live-evals.md) page (for example, `Helpfulness`).
- **Sample rate** — the fraction of matching runs to judge, so you can keep coverage (and cost) proportionate on a busy agent.
- **Enabled** — the toggle that turns continuous scoring on. Leave it off while you dry-run (see below), then turn it on and save.

## Dry-run before you enable

Before committing a scorer, use **Dry-run on recent runs** to preview it against a handful of the agent's most recent real runs. After a few seconds you'll see a card per run with the score the judge gave and its reasoning — for example, *"the response is empathetic and gives a clear next step."*

Nothing is written back during a dry-run and no quota is spent, so you can iterate freely: read the reasons, adjust the rubric wording, and dry-run again until the scores match your own judgement of those runs. Only then enable the scorer and save. Tuning the rubric against your own traffic first is the recommended loop — it's much easier than guessing a rubric in the abstract.

Once enabled, the platform scores new runs going forward (typically within a minute or two of a run arriving).

## Quota and cost

The preview is **free**, with a hard cap of **10,000 scores per project per month**. When a project reaches the cap, scoring pauses for the rest of the month and resumes at the start of the next month. Sampling and the per-scorer sample rate let you stretch that budget across your busiest agents.

!!! warning "Scores are ordinary telemetry, and count toward your ingest usage"
    Each score Logfire writes back is a real `gen_ai.evaluation.result` log event ingested into your project, exactly like a span your application sends. That is deliberate — it's what makes scores queryable, dashboardable, and alertable with no separate storage — but it does mean **scored runs add to your project's ingested data, and to your ingest usage**, the same way any other telemetry does. At 10,000 scores per project per month the volume is small, but it is not zero, and it counts.

## Viewing scores

Scores are standard evaluation events, so every surface that renders online evals renders scorer output too:

- **Live Evaluations** — open **Evals: Live Monitoring** from the sidebar. Your agent appears as a target with a row for the scorer's **Score name**, showing the average score, an event count, and a sparkline over the selected window. See the [Live Evaluations guide](live-evals.md) for what each column means and how to hide evaluators you no longer want listed.
- **Trace view** — each score appears as a `gen_ai.evaluation.result` event nested under the agent-run span it scored, so you can jump from a low score straight to the prompt, tool calls, and response that produced it.
- **SQL (Explore)** — because scores are telemetry, you can query them directly, as shown below.

Open [Explore](explore.md) and run:

```sql
SELECT
  attributes->>'gen_ai.evaluation.target'      AS target,
  attributes->>'gen_ai.evaluation.name'        AS eval_name,
  attributes->>'gen_ai.evaluation.score.value' AS score,
  attributes->>'gen_ai.evaluation.explanation' AS reason
FROM records
WHERE span_name = 'gen_ai.evaluation.result' AND kind = 'log'
ORDER BY start_timestamp DESC
```

You'll get one row per scored run, with the agent name, the score name, the numeric score, and the judge's reason. From here the usual tools apply — build a [dashboard](dashboards.md) panel that trends the average score over time, or set an [alert](alerts.md) that fires when it drops below a threshold.
