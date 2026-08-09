---
title: "Logfire vs. Braintrust"
description: "Compare Logfire and Braintrust for AI evaluation, production observability, pricing, querying, prompts, and human review."
---

# Logfire vs. Braintrust

Braintrust is built around LLM evaluation. Logfire gives you serious evaluation workflows without separating them from the application, services, and infrastructure that produced the result.

If you already have a Braintrust evaluation suite, you do not need to rewrite it to try Logfire. Point a verified Python or TypeScript `Eval` flow at Logfire, run it as usual, and review the resulting experiments and traces in the Logfire UI. Follow [Move from Braintrust to Logfire](migrate-from-braintrust.md) for the two-variable switch.

## Quick comparison

| Capability | Logfire | Braintrust |
| --- | --- | --- |
| Primary focus | AI evaluation plus full-stack observability | AI evaluation and LLM observability |
| Existing Braintrust `Eval` code | Compatibility preview for verified Python and TypeScript flows | Native |
| Offline evaluations | Pydantic Evals in code, with datasets, experiments, comparisons, and case review in Logfire | SDK, UI, playground, remote evaluation, and CI workflows |
| Production evaluation | Pydantic AI online evaluators and Live Evaluations | Server-side online scoring rules |
| Evaluator results | Assertions, numeric scores, and categorical labels | Numeric scorers and categorical classifiers |
| Human review | Run annotations and annotation queues | Human review, assignments, labels, corrections, and datasets |
| Production context | AI calls, agents, HTTP services, databases, browser activity, logs, metrics, and infrastructure | AI application traces, scores, and project logs |
| Telemetry | OpenTelemetry-native traces, logs, and metrics | Braintrust spans and scores, with OpenTelemetry ingest |
| Querying | PostgreSQL-compatible SQL across evaluation and application telemetry, plus MCP access | SQL and BTQL over Braintrust resources |
| Prompt iteration | Prompt Playground and Prompt Management | Playgrounds, hosted prompts, and deployment environments |
| Model routing | Logfire AI Gateway | Braintrust gateway and proxy |
| Usage billing | Telemetry records, with no separate fee for evaluator scores | Processed data, evaluator scores, and retention |

## When to choose Logfire

- **You want the evidence behind a failed evaluation.** Follow a case into its model calls, tool calls, retrieval, database work, HTTP requests, logs, and infrastructure telemetry.
- **You want one system for development and production.** Compare offline experiments, monitor live evaluators, annotate real agent runs, and investigate the surrounding application from the same project.
- **You want to query freely.** Use PostgreSQL-compatible SQL for joins, common table expressions, window functions, dashboards, and alerts, or let a coding agent investigate through the Logfire MCP server.
- **You want OpenTelemetry-native observability.** Instrument the application once and keep the data useful beyond a single AI framework or evaluation SDK.
- **You already have Braintrust eval code.** Redirect a compatible suite first, judge the experience with your own data, and move to native Pydantic Evals only when it improves your code.
- **You do not want evaluator coverage to create a separate score bill.** Logfire meters telemetry records rather than charging for every evaluator result.

## When Braintrust may fit better

- **Your workflow depends on Braintrust-hosted resources.** Braintrust provides hosted datasets, prompts, functions, remote evaluations, and server-side scoring rules that Logfire's compatibility endpoint does not translate.
- **You want Braintrust's managed evaluation environment.** Its playground, Loop agent, dataset snapshots, and UI-run workflows are designed around Braintrust resources.
- **Your team wants an AI-centered system.** If application and infrastructure observability belong elsewhere by design, Braintrust's product boundary may match that workflow.

## Why teams move evaluation work to Logfire

### The average score is the start of the investigation

Both products can show that an experiment regressed. The useful next question is why.

In Logfire, an experiment case is a trace in the same system as the work behind it. When that work is instrumented, you can move from a failed evaluator to the prompt, model response, retrieval context, tool failure, slow query, downstream timeout, or service error without reconstructing the request in another observability product.

That same connection works in the other direction. A surprising production run can become a reviewed example, a dataset case, or evidence for the next evaluation cycle.

### More evaluators do not create a new billing dimension

Braintrust meters [scores and processed data separately](https://www.braintrust.dev/pricing). Its public Starter plan includes 10,000 scores and then charges $2.50 per 1,000; Pro includes 50,000 and then charges $1.50 per 1,000.

Logfire does not have a separate score meter. Evaluator results travel with the experiment telemetry. Logfire includes 10 million logs, spans, and metrics each month, then charges [$2 per million additional records](https://pydantic.dev/pricing) on Team and Growth plans.

The units are not identical, so a universal cost conversion would be misleading. The practical difference is simpler: adding another evaluator changes Braintrust score usage, while Logfire does not add a per-score charge.

### SQL gives people and coding agents the same investigative surface

Logfire exposes [PostgreSQL-compatible SQL](../reference/sql.md) over evaluation and application telemetry. You can join related data, use common table expressions and window functions, turn a query into a dashboard or alert, and give a coding agent the same access through the [Logfire MCP server](../how-to-guides/mcp-server.md).

Braintrust provides SQL and Braintrust Query Language (BTQL) over its projects, experiments, datasets, and logs. Its built-in views and Loop agent keep that investigation inside Braintrust's AI development model.

### You can evaluate Logfire with your existing suite

Most migrations ask you to rewrite the workload before you can judge the destination. Logfire's Braintrust compatibility endpoint gives verified Python and TypeScript `Eval` suites a shorter path:

1. Change the Braintrust app URL and API key environment variables.
2. Run the same evaluation command.
3. Review the completed experiment in Logfire.
4. Decide which datasets, evaluators, prompts, and production workflows are worth moving to native Logfire and Pydantic APIs.

The endpoint does not contact Braintrust, import historical data, or pretend to support every hosted Braintrust feature. The [migration guide](migrate-from-braintrust.md) documents the exact supported boundary and the native replacement for each surrounding workflow.

## Summary

**Choose Logfire** when evaluations need to connect to production behavior, SQL analysis, coding-agent workflows, and the rest of your observability data, or when you want to test the move with existing Braintrust `Eval` code.

**Choose Braintrust** when Braintrust-hosted evaluation resources and its managed AI-only workflows are the product you want.

Ready to compare with your own suite? [Send your next Braintrust evaluation to Logfire](migrate-from-braintrust.md).
