---
title: "Datasets and experiments"
description: "Curate repeatable test cases, review experiment results, and compare changes in the Logfire evaluation workspace."
---

# Datasets and experiments

Use the Logfire evaluation workspace to answer two questions: what should you test, and did the latest change help?

A **dataset** is a reusable collection of test cases. Each case has an input and can also have an expected output and metadata. An **experiment** is one run of your AI system over a dataset. Evaluators judge each result and record assertions or scores that Logfire can aggregate and compare.

## Follow the evaluation loop

1. **Curate cases.** Keep cases in a hosted dataset that your team edits in Logfire, or define them with your eval code.
2. **Run an experiment.** Use [pydantic-evals](evals-in-code.md) to run the same task and evaluators over every case.
3. **Read the overview.** Check completion, assertions, task errors, evaluator results, duration, tokens, and cost.
4. **Review case evidence.** Inspect the input, output, evaluator result, and trace for failures or surprising scores.
5. **Compare iterations.** Choose a baseline run and confirm whether a candidate improved the cases that matter.

## Choose where cases live

The **New dataset** flow asks how you want to manage cases:

- **Manage in Logfire** creates a hosted dataset. Your team can add and edit cases in the web UI, define JSON schemas, import cases from code, and add production traces.
- **Manage in code** keeps the source of truth with your eval code. Experiment results still appear in Logfire. You can also sync a copy of the cases to Logfire when you want to browse or edit them there.

Use stable dataset names so successive runs appear together. Names can contain `/`, which lets the Datasets page group related datasets by path prefix.

## Use the workspace

- [Manage datasets](manage-datasets.md) to find, create, import, and edit test cases.
- [Run evals in code](evals-in-code.md) to execute a task and send results to Logfire.
- [Review experiments](review-experiments.md) to diagnose failures and compare a candidate with a baseline.
- Use the [Datasets SDK](datasets-sdk.md) to create, publish, and fetch hosted datasets from Python.

## Consequences to know

- Configuring Logfire during an eval sends its inputs, outputs, evaluator results, and traces to your project.
- Experiments run from code. The web UI helps you prepare datasets and analyze results; it does not execute the task under test.
- Code remains the source of truth for code-defined cases. Syncing imports new cases into the hosted copy and updates cases with matching names; edits in Logfire do not change your code.
- Every experiment is also trace data. Open a case's trace when the result alone does not explain what the agent did.

## Next steps

Start with [Manage datasets](manage-datasets.md) if you need cases. If you already have a dataset and results, go directly to [Review experiments](review-experiments.md).
