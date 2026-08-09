---
title: "Review AI outputs by hand"
description: "Add human judgment to agent runs in Pydantic Logfire by reviewing runs directly or working through an annotation queue."
---

# Review AI outputs by hand

Review an agent run when code and model-based evaluators cannot decide whether the result was helpful, safe, or appropriate.

A **run annotation** is editable reviewer feedback attached to one end-to-end agent invocation. It can record a pass, neutral, or fail verdict, plus a comment and tags that explain the decision. Run annotations are human-review evidence, not automated evaluator results, and they do not roll into experiment or Live Evaluation aggregates.

## When to use human review

- Build a hand-labeled set for checking whether an LLM judge agrees with your reviewers.
- Investigate production interactions where automated signals are missing or ambiguous.
- Identify failures worth preserving as cases in a repeatable [dataset](datasets-and-experiments.md).
- Apply a shared review criterion across a sample of agent runs.

## Choose direct review or a queue

### Review one run

Use direct review when you are investigating one run or a small sample. Open the run, inspect its messages, model calls, tool calls, and output, then save your judgment. Follow [Annotate an agent run](annotate-agent-runs.md) for the complete workflow.

!!! note "Run annotations are in Beta"

    Run annotations are available in every project, but the workflow may change while it is in Beta.

### Work through an annotation queue

Use an **annotation queue** when review needs to be systematic. A queue gives reviewers a curated list of agent runs to inspect one after another instead of asking them to find runs manually. Teams can use queues for a random quality sample or for interactions selected by another signal.

!!! note "Annotation queues are a Design Partner feature"

    Annotation queues are available to Design Partner customers participating in the early-access program.

## Make the judgment reusable

Agree on one sentence that defines the criterion before reviewing. For example: "The answer resolves the customer's question without inventing details."

For each run:

1. Choose **Pass**, **Neutral**, or **Fail** using that criterion.
2. Add a comment that identifies the evidence behind the verdict.
3. Add tags such as `hallucination`, `tone`, or `tool-error` when they will help reviewers find related cases.

Use the resulting annotations as calibration data for automated evaluators or as leads for new dataset cases. Adding a failing production interaction to a dataset lets future offline experiments check that behavior again.

## Consequences to know

- **Run annotations are stored in Logfire.** A saved verdict, comment, and tags are sent to your Logfire project and remain visible to your team.
- **Comments can contain user data.** Treat comments like other production data. Do not copy sensitive information into them.

## Next steps

- [Annotate an agent run](annotate-agent-runs.md): review one interaction and save a verdict.
- [Manage datasets](manage-datasets.md): preserve reviewed failures as repeatable test cases.
- [Run an evaluation](evals-in-code.md): measure a fixed dataset with automated evaluators.
- [Live Evaluations](live-evals.md): monitor automated evaluator results from production traffic.
