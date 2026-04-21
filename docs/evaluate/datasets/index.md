---
title: "Datasets: Build and Manage Evaluation Test Cases"
description: "Create, manage, and fetch typed evaluation datasets in Pydantic Logfire. Integrate with pydantic-evals to run evaluations against your AI systems."
---

# Datasets

Datasets let you build and maintain collections of test cases for evaluating your AI systems. You can create datasets through the Logfire web UI or programmatically via the SDK, then fetch them as [pydantic-evals](https://ai.pydantic.dev/evals/) `Dataset` objects to run evaluations.

!!! note "Relationship with Pydantic Evals"

    Datasets in Logfire are the server-side complement to [pydantic-evals](https://ai.pydantic.dev/evals/) file-based datasets. While pydantic-evals stores datasets as local YAML files, Logfire datasets are stored on the server and can be created from production traces, edited collaboratively in the UI, and fetched for evaluation. The SDK is designed so you can move seamlessly between the two.

## Hosted vs Local Datasets

When you open the **Evals** page, you'll see two types of datasets:

- **Hosted** datasets have their cases stored and editable on Logfire. You create these through the UI or SDK, and can add, edit, and delete individual test cases.
- **Local** datasets are discovered automatically from experiment runs in your code (via `pydantic-evals`). They appear in the list alongside hosted datasets but their cases are read-only --- they reflect what your code defined. If you run an experiment without defining a `dataset_name` in code, it still appears in the list using the experiment ID as a fallback name.

A dataset can be both: if you create a hosted dataset with the same name as one in your code, they merge into a single entry with both hosted cases and experiment history.

You can filter between these types using the **Hosted** and **Local** tabs at the top of the datasets list.

## What is a Hosted Dataset?

A Hosted Dataset is a collection of test cases stored on the Logfire server. Each hosted dataset row is one **case** with inputs, expected output, and optional metadata. Additionally, a **schema** for the whole hosted dataset can be defined which constrains each case — ensuring that every case has the correct structure.

```
┌─────────────────────────────────────────────────────────────────────┐
│ Hosted Dataset                                                      │
│                                                                     │
│  ┌──────────────────────────────────┐  ┌─────────────────────────┐  │
│  │ Case #1                          │  │ Schema (Optional)       │  │
│  │   Input                          │  │   Input                 │  │
│  │   Expected Output                │  │   Expected Output       │  │
│  │   Metadata                       │  │   Metadata              │  │
│  └──────────────────────────────────┘  │                         │  │
│  ┌──────────────────────────────────┐  │                         │  │
│  │ Case #2                          │  │                         │  │
│  └──────────────────────────────────┘  │                         │  │
│  ┌──────────────────────────────────┐  │                         │  │
│  │ Case #3                          │  │                         │  │
│  └──────────────────────────────────┘  └─────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
```

Hosted datasets integrate into the broader [pydantic-evals](https://ai.pydantic.dev/evals/) data model:

```
Hosted Dataset (1) ─────────── (Many) Case
│                                │
│                                │
└── (Many) Experiment ──── (Many) Case results
     │
     ├── (1) Task
     │
     └── (Many) Evaluator
```

A single hosted dataset contains many cases. Over time, you run multiple experiments against the same hosted dataset — each experiment executes every case against a task and scores the results with evaluators.

## Why Datasets?

When evaluating AI systems, you need test cases that reflect real-world usage. Datasets solve several problems:

- **Production-driven test cases**: Create test cases directly from production traces using the "Add to Dataset" action in Live View, so your evaluations reflect real user inputs.
- **Collaborative editing**: Team members can add, review, and refine test cases through the web UI without touching code.
- **Typed schemas**: Define input, output, and metadata schemas so that every case is validated, preventing malformed test data.
- **SDK integration**: Fetch datasets as typed [`pydantic_evals.Dataset`][pydantic_evals.Dataset] objects and run evaluations with a single method call.

## The Evaluation Workflow

Datasets fit into a continuous evaluation loop:

1. **Observe** production behavior in Live View.
2. **Curate** test cases by adding interesting traces to a dataset.
3. **Evaluate** your system against the dataset using pydantic-evals.
4. **Analyze** the results in the Logfire Evals tab.
5. **Improve** your system and repeat.

## Next Steps

- **[Web UI Guide](ui.md)** --- Create and manage datasets through the Logfire interface.
- **[SDK Guide](sdk.md)** --- Manage datasets programmatically with Python.
- **[Running Evaluations](evaluations.md)** --- Fetch datasets and run evaluations with pydantic-evals.
- **[SDK Reference](../../reference/api/datasets.md)** --- Complete method and exception reference.
