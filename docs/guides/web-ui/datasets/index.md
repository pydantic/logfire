---
title: "Managed Datasets: Build and Manage Evaluation Test Cases"
description: "Create, manage, and export typed evaluation datasets in Pydantic Logfire. Integrate with pydantic-evals to run evaluations against your AI systems."
---

# Managed Datasets

!!! warning "Experimental Feature"

    Managed datasets are an experimental feature currently gated behind a feature flag. Reach out to us on [Slack](https://logfire.pydantic.dev/docs/join-slack/) or [contact us](../../../help.md) to learn how to enable it for your project.

Managed datasets let you build and maintain collections of test cases for evaluating your AI systems. You can create datasets through the Logfire web UI or programmatically via the SDK, then export them as [pydantic-evals](https://ai.pydantic.dev/evals/) `Dataset` objects to run evaluations.

!!! note "Relationship with Pydantic Evals"

    Managed datasets are the server-side complement to [pydantic-evals](https://ai.pydantic.dev/evals/) file-based datasets. While pydantic-evals stores datasets as local YAML files, managed datasets are stored in Logfire and can be created from production traces, edited collaboratively in the UI, and exported for evaluation. The SDK is designed so you can move seamlessly between the two.

## Why Managed Datasets?

When evaluating AI systems, you need test cases that reflect real-world usage. Managed datasets solve several problems:

- **Production-driven test cases**: Create test cases directly from production traces using the "Add to Dataset" action in Live View, so your evaluations reflect real user inputs.
- **Collaborative editing**: Team members can add, review, and refine test cases through the web UI without touching code.
- **Typed schemas**: Define input, output, and metadata schemas so that every case is validated, preventing malformed test data.
- **SDK integration**: Export datasets as typed `pydantic_evals.Dataset` objects and run evaluations with a single method call.

## The Evaluation Workflow

Managed datasets fit into a continuous evaluation loop:

1. **Observe** production behavior in Live View.
2. **Curate** test cases by adding interesting traces to a managed dataset.
3. **Evaluate** your system against the dataset using pydantic-evals.
4. **Analyze** the results in the Logfire Evals tab.
5. **Improve** your system and repeat.

## Next Steps

- **[Web UI Guide](ui.md)** --- Create and manage datasets through the Logfire interface.
- **[SDK Guide](sdk.md)** --- Manage datasets programmatically with Python.
- **[Running Evaluations](evaluations.md)** --- Export datasets and run evaluations with pydantic-evals.
- **[SDK Reference](sdk-reference.md)** --- Complete method and exception reference.
