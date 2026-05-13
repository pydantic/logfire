---
title: "Logfire Evals: View & Analyze Evaluation Results"
description: "Logfire Evals provides observability into how your AI systems perform. View, compare and analyze evaluation results in the Pydantic web UI."
---
# Evals

This is the reference for the **Evals: Datasets & Experiments** page in the Logfire web UI — use it to view and compare your dataset and experiment results. For live, per-request evaluation activity streaming in from production or staging traffic, see [Live Evaluations](./live-evals.md) instead.

**Where to go next:**

- To get started with creating and running evals in code, see the [Pydantic Evals docs](https://pydantic.dev/docs/ai/evals/evals/).
- To create or edit datasets through the Logfire UI, see the [Datasets Web UI Guide](../../evaluate/datasets/ui.md). This page covers what you see on the Evals page itself; the Web UI Guide covers dataset/case lifecycle tasks (create, edit, manage cases, export).
- For programmatic dataset access, see the [SDK Guide](../../python-sdk/evaluate/datasets.md).

## The Datasets List

Click **Evals: Datasets & Experiments** in the sidebar to open the datasets list. This is the top-level view for all dataset-and-experiment evaluation activity in your project. For live, per-request evaluation activity streaming in from production or staging, see [Live Evaluations](./live-evals.md) instead.

Each dataset row shows:

- **Name** --- the dataset identifier (with a **hosted** badge for hosted datasets)
- **Pass rate** --- aggregate pass rate from the most recent experiments
- **Last run** --- when the most recent experiment was run
- **Experiments** --- total number of experiment runs
- **Cases** --- number of test cases in the dataset

Use the **All**, **Hosted**, and **Local** tabs to filter by dataset source. The search bar filters by name.

If you haven't created any datasets yet, the empty state guides you through two paths: creating a hosted dataset in the UI, or running evals from code with `pydantic-evals`.

## Dataset Detail Page

Click a dataset name to open its detail page. The page has tabs for:

- **Experiments** --- all evaluation runs against this dataset
- **Cases** --- test cases (editable for hosted datasets)
- **Schema** --- input, output, and metadata schemas

The header shows the dataset name, experiment count, case count, and aggregate pass rate. Use the **Export** button to download cases, the **Edit** button to modify the dataset, or the **`<> SDK`** button to view code snippets for working with this dataset programmatically.

If the dataset has no experiments yet, the empty state walks you through the setup: define your schema, add test cases, then run your first experiment from code.

## Viewing Experiments

The **Experiments** tab lists all evaluation runs for the dataset. Each experiment shows results in a grid with inputs, outputs, scores, and assertion results.

Click any experiment row to see detailed results including:

- **Test cases** with inputs, expected outputs, and actual outputs
- **Assertion results** --- pass/fail status for each evaluator
- **Performance metrics** --- duration, token usage, and custom scores
- **Evaluation scores** --- detailed scoring from all evaluators

## Comparing Experiments

To compare multiple runs side by side:

1. Select experiments from the list using the checkboxes
2. Click **Compare**
3. View side-by-side results for the same test cases

The comparison view highlights differences in outputs, score variations, performance changes, and regressions between runs.

## Integration with Traces

Every evaluation experiment generates detailed OpenTelemetry traces that appear in Logfire:

- **Experiment span** --- root span containing all evaluation metadata
- **Case execution spans** --- individual test case runs with full context
- **Task function spans** --- detailed tracing of your AI system under test
- **Evaluator spans** --- scoring and assessment execution details

Navigate from experiment results to full trace details using the span links.
