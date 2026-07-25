---
title: "Datasets and experiments"
description: "Build evaluation datasets from production traces or the SDK, run experiments against them, and compare results in the Pydantic Logfire web UI."
---

# Datasets and experiments

A **dataset** is a collection of test cases (inputs, and optionally the output you expect) that you evaluate your AI system against. An **experiment** is one run of your system over that dataset, producing a table of [scores](overview.md) you can line up against previous runs. Together they are how you answer "did that change help?" with numbers instead of a re-read.

This page covers building and running datasets from the Logfire web UI. To do the same from code, see [Evals in code](evals-in-code.md); for the concepts (scorers, scores, offline vs online), start with the [evals overview](overview.md).

## Hosted vs local datasets

When you open the **Evals: Datasets & Experiments** page in the sidebar, you see two kinds of dataset:

- **Hosted** datasets have their cases stored and editable on Logfire. You create them in the UI or via the [SDK](datasets-sdk.md), and can add, edit, and delete individual cases. Reach for a hosted dataset when non-engineers need to edit cases, or when a team wants one shared set to evaluate against.
- **Local** datasets are discovered automatically from experiment runs in your code (via [pydantic-evals](https://pydantic.dev/docs/ai/evals/evals/)). They appear in the list alongside hosted datasets, but their cases are read-only: they reflect what your code defined. Reach for a local dataset when the cases belong with your source. A run with no `dataset_name` still appears, using its experiment ID as a fallback name.

A dataset can be both. Create a hosted dataset with the same name as one in your code and they merge into a single entry with both hosted cases and experiment history. Use the **All**, **Hosted**, and **Local** tabs at the top of the list to filter by source.

Because cases can come from real traces, edited by anyone on the team, and validated against a typed schema, your evaluations stay grounded in real usage rather than a handful of examples someone made up once.

## Create and manage a dataset in the UI

All tasks below start from the **Evals: Datasets & Experiments** page in the sidebar.

- **Create**: click **+ New dataset** and enter a name (or type a name into the empty state and click **Create**). Then edit it to add a description and schemas.
- **Edit**: on the dataset detail page, click **Edit**. The **General** section holds name and description; the **Schemas** section defines JSON schemas for inputs, expected outputs, and metadata. Use the **Generate schema** toggle to have Pydantic AI draft the schemas from a plain-language description of your data shape.
- **Manage cases**: on the **Cases** tab, click **+ Add case** to open the editor (with labeled, typed fields when a schema is defined, raw JSON otherwise), the pencil icon to edit, or the trash icon to delete.
- **Export**: click **Export** to download as raw **JSON** or as a **pydantic-evals** YAML file compatible with `pydantic_evals.Dataset.from_file()`.

!!! tip "Prefer the SDK when your schema is Python types"
    If your inputs and outputs are already Python types (dataclasses, Pydantic models), publishing the dataset from code is easier: the SDK generates the hosted JSON schemas from your type definitions. See [Evals in code](evals-in-code.md) and the [Datasets SDK reference](datasets-sdk.md).

### Add cases from production traces

The highest-signal test cases are the ones your real users produced:

1. Open the [live view](../guides/web-ui/live.md) and find a span that represents a good test case.
2. Click the database icon (**+**) on the span details panel.
3. Select an existing dataset or create a new one.
4. Review the inputs and outputs the AI extracts from the span, edit if needed, and save.

This keeps a link back to the source trace, so you always know where a case came from.

## Run and view experiments

Experiments are always run from Python (see [Evals in code](evals-in-code.md)); with `logfire.configure()` set, their results appear here automatically. Open a dataset to see its detail page, which has tabs for **Experiments** (all runs), **Cases** (editable for hosted datasets), and **Schema**. The header shows the experiment count, case count, and aggregate pass rate. The **Export**, **Edit**, and **`<> SDK`** buttons download cases, modify the dataset, or show code snippets for working with it programmatically.

The **Experiments** tab lists every run. Click one to see each case's inputs, expected and actual outputs, per-evaluator pass/fail assertions, performance metrics (duration, token usage), and detailed scores.

### Compare experiments

To see whether a change helped or hurt, put two runs side by side:

1. Select experiments with the checkboxes.
2. Click **Compare**.
3. Read the side-by-side results for the same cases.

The comparison highlights output differences, score variations, performance changes, and regressions between runs.

!!! tip "Link to a comparison from code"
    `logfire.url_from_eval(report)` takes a `pydantic_evals` report and returns the URL to view it in the web UI, or `None` if the project URL or trace and span IDs are not available (for example when Logfire was not configured when the report was created).

## Every experiment is also a trace

Each experiment emits OpenTelemetry traces you can open in Logfire: a root **experiment span** with the run's metadata, a **case span** per test case, **task spans** tracing your system under test, and **evaluator spans** for each scorer. From any experiment result you can jump straight to the full trace, so a low score takes you to the exact prompt, tool calls, and response that produced it.

## Next steps

- **[Evals in code](evals-in-code.md)**: run experiments and print a real score table with pydantic-evals.
- **[Datasets SDK](datasets-sdk.md)**: create, publish, and fetch datasets programmatically.
- **[Live evals](live-evals.md)**: score real production traffic as it happens.
- **[Human review](human-review.md)**: turn human judgment into scores that sit next to your automated ones.
