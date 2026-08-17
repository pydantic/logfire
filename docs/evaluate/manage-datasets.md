---
title: "Manage datasets"
description: "Create a hosted or code-defined evaluation dataset, curate its cases, and keep a large dataset list usable."
---

# Manage datasets

Build a dataset, a stable collection of test cases that you can run repeatedly as your agent, model, or prompt changes.

Open a project, then select **AI Evaluations** > **Datasets & experiments**. The **Datasets** tab lists both kinds of dataset together.

## Understand what the list contains

The list combines two sources, keyed on the dataset name:

- **Hosted** datasets are records stored on Logfire. They are always listed, whatever time range you have selected.
- **Code-defined** datasets are not stored as records at all. Logfire derives them from the experiments that ran against them, so a code-defined dataset appears once an experiment reports its name, and only while that experiment falls inside the selected time range.

A name that exists in both sources is **one row, not two**. Creating a hosted dataset named `support/routing` when your code already runs experiments under that name merges them: the row shows the hosted cases and the experiment history together, marked **Hosted**. This is why stable names matter. A name that changes between runs produces a new row each time instead of accumulating history under one.

## Find the dataset you need

Use the controls above the list to narrow a large project:

- Search for a dataset name.
- Filter **Type** to **Hosted** or **Code-defined**.
- Set **Group by** to **Type**, **Path prefix**, or **None**.
- Change the time range if an older code-defined dataset is missing.

Choose stable, descriptive names. Use names such as `support/routing` and `support/response-quality` when path-prefix grouping will help your team navigate related datasets.

![Find datasets by name, type, or path prefix](../images/guide/evals/datasets-list.webp)

Each row shows the actions available for that dataset. **Edit cases** is available when cases are hosted in Logfire. **Review experiments** opens the runs associated with that dataset.

If code creates many temporary dataset names, select **Hide for me** on entries you do not need. This changes only your view. Use **Hidden** above the list to restore them later.

## Choose how to manage a new dataset

Select **New dataset**, then choose where the source of truth should live:

- **Manage in Logfire** when teammates need to curate cases in the web UI or you want a shared hosted dataset.
- **Manage in code** when cases belong with the source and review process for your application.

If you manage the dataset in code, choose whether to **Sync cases to Logfire** or **Keep cases in code**. Experiment results can appear in Logfire with either choice when you configure Logfire for the run. Syncing also makes the cases available to browse and edit in Logfire.

![Choose how to manage a new dataset](../images/guide/evals/new-dataset.webp)

## Create a hosted dataset

The hosted-dataset flow has three steps:

1. **Dataset**: enter a stable name and an optional description.
2. **Schemas**: optionally define JSON schemas for inputs, expected outputs, and metadata.
3. **First case**: optionally add an initial input, expected output, and metadata.

You can skip schemas and the first case. Add them later when the shape becomes clear.

After creation, use the **Cases** tab to maintain the dataset:

- **Add case** creates a case in the web UI.
- **Add cases from code** opens a prefilled `add_cases(...)` snippet for appending or updating individual cases.
- **Sync cases from code** opens a prefilled `push_dataset(...)` snippet for publishing a whole local dataset.
- **Export** downloads the cases for reuse outside Logfire.
- **Edit** changes the dataset name, description, or schemas.

![Edit the cases in a hosted dataset](../images/guide/evals/hosted-dataset-cases.webp)

**Add cases from code** and **Sync cases from code** both open a code snippet for you to run. Neither transfers anything on its own. Both snippets arrive prefilled with the dataset's name and the type names taken from its schemas, so the difference between them is only which SDK call they hand you: `add_cases(...)` appends to what is already there, and `push_dataset(...)` publishes a local `Dataset` as a whole. See the [Datasets SDK](datasets-sdk.md) for both.

If Logfire already discovered a code-defined dataset with the same name, creating its hosted counterpart can import the latest cases instead of starting empty. Review the imported cases before relying on them as a shared test set.

## How cases get into a hosted dataset

Cases reach a hosted dataset three ways. They combine freely in one dataset:

| Path | Volume | Use it when |
| --- | --- | --- |
| [Live view](#add-a-case-from-a-production-trace) | One case per span | A real request is worth keeping as a regression case |
| [The Cases tab](#create-a-hosted-dataset) | One case at a time | You are hand-writing a specific edge case |
| [The SDK](datasets-sdk.md) | Bulk | Cases are generated, migrated, or already in code |

Adding from Live view is the path that turns production behavior into test cases, and it is usually where a shared dataset starts. The SDK is the only path that scales to many cases at once.

A hosted dataset holds at most **10,000 cases**. Adding a case beyond that limit is rejected, including in bulk, so a large import needs splitting across datasets.

### Schemas are enforced on every write

If a dataset defines schemas, they are enforced on every write, not just used as a hint for teammates. Logfire validates each case against them whenever you add, update, or import one, through the UI and the SDK alike, and rejects the whole request when a field does not match. The error names the failing field and the reason.

Two details matter when you plan a schema:

- Only fields that are present are validated. A schema on `expected_output` or `metadata` does not force a case to carry one; it constrains the value when a case does.
- Schemas are enforced from the moment you define them, but they are not applied retroactively. Cases that predate a schema stay as they are, and you find out they no longer match the next time something writes to them.

Define schemas once the shape of a case has settled. Adding them early to a dataset you are still exploring turns every subsequent write into a validation error.

## Add a case from a production trace

Production failures and surprising outputs make useful regression cases:

1. Open [Live view](../guides/web-ui/live.md) and select the span you want to preserve.
2. Select the database icon (**+**) in the span details.
3. Choose an existing hosted dataset or create one.
4. Review the extracted input, expected output, and metadata, then save the case.

The case keeps a link to its source trace, so reviewers can inspect the original behavior.

## Verify the dataset

Before running an experiment, confirm that:

- the dataset has a stable name that future runs will reuse;
- hosted cases have the expected input and optional expected output;
- schemas match the cases already in the dataset, so later writes are not rejected;
- the dataset appears in the intended path-prefix group;
- **Review experiments** opens the expected run history.

## Troubleshooting

### A code-defined dataset has no browsable cases

This is expected when the cases remain only in code. Use **Sync cases to Logfire**, or create a hosted dataset with the same name and import the latest cases.

### A dataset is missing

Widen the time range and clear the type filter. Also check **Hidden** if you previously hid the dataset for yourself.

If the project has a very large number of dataset names, the list is capped and keeps the most recently active names, so an older one can fall outside it. Search by name rather than scrolling: the search runs before the cap is applied, so it reaches datasets the list itself does not show.

A code-defined dataset also disappears once all of its experiments are archived, because nothing is left to derive it from. Hosted datasets are unaffected. Restore the dataset by unarchiving an experiment, or create a hosted dataset with that name to keep it in the list permanently.

### A dataset is named `Untitled`

An experiment that reports no dataset name is grouped under a single placeholder rather than being dropped. Every unnamed run in the project collects into that one row, so it is a mixture rather than a dataset. Set a `name` on the `Dataset` in your eval code to separate the runs.

### The list contains many one-off datasets

Use **Group by: Path prefix** for consistently named datasets. Hide temporary entries for yourself, then change the code to reuse stable names for future runs.

### Adding a case fails validation

The dataset has schemas and the case does not match one of them. The error names the field and the reason. Either correct the case, or relax the schema under **Edit** if the dataset's shape has genuinely changed. Existing cases are not rechecked when you change a schema, so a dataset can hold cases that would no longer be accepted.

## Next steps

[Run an eval](evals-in-code.md) against the dataset, then [review the experiment](review-experiments.md) in Logfire.
