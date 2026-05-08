---
title: "Live Evaluations: Monitor AI Systems in Production"
description: "View real-time online-evaluation activity for your agents and functions in Pydantic Logfire. Track pass rates, categorical labels, and numeric scores across production traffic."
---
# Live Evaluations

The **Evals: Live Monitoring** page streams evaluator results from live application traffic (e.g., from a production deployment) into the Pydantic Logfire web UI. Every target that emits evaluation events appears here as a single row, with a sparkline for each attached evaluator and a summary of activity over the selected time window. This is the Logfire view of what Pydantic AI calls [online evaluation](https://ai.pydantic.dev/evals/online-evaluation/).

To wire up evaluators on the Python side, see the [Online Evaluation guide](https://ai.pydantic.dev/evals/online-evaluation/) in the Pydantic AI docs. The page renders any ingested `gen_ai.evaluation.result` OpenTelemetry events that follow the [GenAI evaluation semantic conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/gen-ai-events/#event-gen_aievaluationresult) — the [`@evaluate`](https://ai.pydantic.dev/evals/online-evaluation/#quick-start) decorator and the [`OnlineEvaluation`](https://ai.pydantic.dev/evals/online-evaluation/#agent-integration) agent capability from `pydantic-evals` are the supported entry points today.

## The Directory

Click **Evals: Live Monitoring** in the sidebar to open the directory. Each row is one **target** — the name of the function or agent that produced the evaluation event. Expanding a row (via the chevron on the left) reveals a larger sparkline for each of its evaluators.

Each row shows:

- **Target** — the target name, with an agent or function icon
- **Type** — `agent` or `function`. Evaluations dispatched by the [`OnlineEvaluation`](https://ai.pydantic.dev/evals/online-evaluation/#agent-integration) capability on a Pydantic AI agent appear as `agent`; `@evaluate`-decorated functions appear as `function`, even when the decorated function runs inside an agent
- **Evaluations** — one compact cell per evaluator with a pass rate, numeric average, or categorical label summary plus a sparkline
- **Events** — total number of evaluation events in the window
- **Last activity** — when the most recent event arrived

Use the time-window tabs in the page header (**1h**, **6h**, **24h**, **7d**, **30d**) to adjust the range. Narrowing the window never empties the page: a target that was active anywhere in the last 30 days still appears as a silent row so you can see that evaluators are configured even if traffic is quiet right now.

The column headers are sortable — click **Target**, **Type**, **Events**, or **Last activity** to re-order. The sort state is persisted in the URL so you can share a specific view.

If you haven't wired up any evaluators yet, the empty state shows getting-started snippets for the two entry points (the `@evaluate` decorator for any function, and the `OnlineEvaluation` capability for a Pydantic AI agent). Once events arrive, the same snippets remain accessible via the collapsible **How do I send events here?** strip above the directory.

## Target Detail Page

Click a target row to open its detail page. The page shows:

- Each evaluator attached to the target as its own row, with a larger sparkline, numeric/pass-rate/categorical summary, and an error count when evaluators raised
- A **Recent events** table with the 50 most recent evaluation events for the target

The **Evaluator** filter dropdown narrows the recent-events table to a single evaluator. The time-window tabs behave the same as on the directory.

Each recent-events row includes an **Open trace in live view** link that jumps to the live trace view for the span the evaluation was attached to — useful for seeing the full context of a low-scoring call.

Each evaluator row also shows the distinct `evaluator_version` values seen in the window as small version badges. During a deploy rollout where two versions of the same evaluator are live at once, both versions appear side-by-side. See [Evaluator Versioning](https://ai.pydantic.dev/evals/online-evaluation/#evaluator-versioning) in the Pydantic AI docs for how to set the version tag.

## Evaluator Shapes

The **Evaluations** cell adapts to the shape of scores an evaluator produces:

- **Pass rate** — evaluators that return `bool`. The cell shows a percentage and colors a dot based on health (≥95% green, ≥80% amber, otherwise red).
- **Numeric average** — evaluators that return `int` or `float`. The cell shows the average score over the window.
- **Categorical labels** — evaluators that return a string. The cell shows the most common label with a **`+N`** badge indicating how many other distinct labels were seen.
- **Error-only** — evaluators that only raised in the window. The cell shows the error count in red.

Evaluators that emit multiple score keys (a mapping return type) show up as one row per key.

## Integration with Traces

Each `gen_ai.evaluation.result` event is parented to the span whose call was evaluated, so the evaluation appears nested inside the original function call in the trace view. This makes it easy to jump from a failing evaluator back to the exact prompt, tool calls, and response that produced the result.

The event attributes follow the [OTel GenAI evaluation semantic conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/gen-ai-events/#event-gen_aievaluationresult):

- `gen_ai.evaluation.target` — the function or agent name
- `gen_ai.evaluation.name` — the evaluator name
- `gen_ai.evaluation.score.value` / `gen_ai.evaluation.score.label` — score payload
- `gen_ai.evaluation.explanation` — optional free-text reason
- `gen_ai.evaluation.evaluator.source` — JSON-serialized `EvaluatorSpec` (evaluator class + constructor args). Live Evaluations groups by `(target, name)`, so two events with the same target and name but different sources land in the same row; the `source` is visible on individual events in the trace view so you can tell them apart there
- `gen_ai.evaluation.evaluator.version` — optional version tag so retired evaluator revisions can be filtered out
- `gen_ai.agent.name` — set by the `OnlineEvaluation` capability, and also propagated via OTel baggage onto any evaluation emitted inside a Pydantic AI agent run (useful for drill-down, but not used to classify the target — see the Type column above)
- `error.type` — set when the evaluator raised
