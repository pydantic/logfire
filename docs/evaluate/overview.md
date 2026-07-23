---
title: "Evaluate your AI: measure output quality"
description: "Learn how evaluations work in Pydantic Logfire (datasets, scorers, scores, and experiments) and how to measure AI output quality offline and in production."
---

# Evaluate your AI

Know whether your AI system is getting better or worse, with numbers, not vibes. When you change a prompt, swap a model, or refactor an agent, an evaluation tells you if answer quality went up or down before your users find out.

An **evaluation (eval)** is a repeatable test of an AI system's output quality, like a test suite for software, except the output has no single right answer. Instead of `assertEqual`, an eval attaches a **scorer** (also called an **evaluator**: the thing that judges an output and produces a score) to each answer, and each scorer produces a **score** (one saved quality rating for an output). Collect those scores over a set of test cases and you can compare versions instead of guessing.

## The stakes

Without evals, "did that prompt change help?" is answered by re-reading a handful of outputs and forming an impression. That impression doesn't survive a teammate, a week, or a model upgrade. A regression that only shows up on 1 in 20 inputs is invisible to spot-checking and obvious to an eval. Evals turn "it feels better" into "the pass rate went from 82% to 91% on our 200-case set."

## The scaffold: dataset → task → scorers → score → experiment

Every offline eval in Logfire is built from the same five pieces (online evals reuse only the **scorer** and **score** pieces, applied to live traffic instead of a dataset). Learn them once:

1. **Dataset**: a collection of test cases (inputs and, optionally, expected outputs) you evaluate against.
2. **Task**: your AI system under test: a function that takes a case's input and returns an output (an LLM call, a Pydantic AI agent, your own API).
3. **Scorers (evaluators)**: one or more judges attached to the task. Each looks at an output and produces a score. A scorer can be plain code (exact match, "contains no personally identifiable information (PII)"), an **LLM-as-a-judge** (using a language model to score another model's output), or a human.
4. **Score**: the rating each scorer produces for each output, saved so you can compare and aggregate.
5. **Experiment**: one run of your task over the whole dataset, producing a table of scores you can compare across versions.

In prose, the flow is: the **dataset** feeds each case into your **task**; each output is handed to your **scorers**; each scorer emits a **score**; and the whole pass over the dataset is one **experiment** you can line up against the last one.

## Two ways to hold a dataset

The dataset, the collection of test cases, can live in either of two places, and you can move cases between them:

- **In code**, with [pydantic-evals](datasets/index.md). You define the cases in Python; when you run an experiment with Logfire configured, its results appear in Logfire automatically. This is the right home when your cases are generated from code or checked into your repo alongside your tests.
- **Hosted on Logfire.** You create the dataset in the **Evals → Datasets** screen (click **New dataset**), edit its cases directly in the web UI, give it a schema, and share it with your team. Experiments are still always run from Python. A hosted dataset shows up next to your code-defined ones, and you can import cases from one into the other.

Reach for a hosted dataset when non-engineers need to add or edit test cases, or when a team wants one shared set of cases to evaluate against; reach for a code dataset when the cases belong with your source. See [Datasets](datasets/index.md) for both.

## Offline vs online: a test suite vs monitoring

The two modes use these pieces differently, and the easiest way to hold them apart is an analogy you already know:

- **Offline eval**: running evals against a fixed dataset, like a test suite. You control the inputs, you run it on demand or in continuous integration (CI), and you compare experiments over time. Use this to catch regressions before you ship. See [Run an evaluation](datasets/evaluations.md).
- **Online (live) eval**: scoring real production traffic as it happens, like monitoring. The inputs are whatever your real users sent; scorers run against live outputs and stream results in. Use this to catch quality drops in production that your test set never anticipated. See [Live Evaluations](../guides/web-ui/live-evals.md).

Offline is your test suite; online is your production monitoring. Most teams need both: the test suite proves a change is safe to ship, monitoring proves it stayed good once real traffic hit it.

## The score: one primitive for every kind of judgment

A **score** is the unifying primitive. Whether the rating came from an LLM-as-a-judge, a code check, a human reviewer, or a thumbs-up from an end user, it lands as the same kind of saved score, so all four show up together on the same output and roll up into the same numbers. That means [human review](human-review.md) and user feedback aren't a separate system bolted on the side; they produce scores that sit next to your automated ones.

When you design a scorer, the score's *shape* is the real decision. Reach for the shape that matches the question:

- **Pass/fail (boolean)**: for checks with a clear yes/no: "did it hallucinate?", "does the output contain PII?", "is it valid JSON?" This is the shape to prefer whenever you can express the judgment as a yes/no.
- **Categorical (a label)**: for a small set of known outcomes: `refused` / `answered` / `deflected`, or `low` / `medium` / `high` severity. Use when the answer is one of a few named buckets.
- **Numeric (a number)**: for genuinely continuous judgments like a relevance rating. The most expressive, but the hardest to keep stable. See the best practices below before reaching for a 1–10 scale.

## Best practices, with the reason attached

!!! tip "Prefer binary or categorical scores over 1–10"

    LLM judges are unstable on continuous scales: ask the same judge to rate the same answer "out of 10" twice and you'll often get different numbers, and different judges won't agree on what a 7 means. A yes/no ("is this answer grounded in the source?") or a small set of labels is far more reproducible. Reach for a numeric scale only when the judgment is truly continuous and you've checked the judge is stable on it.

!!! tip "Benchmark your LLM judge before you trust it"

    An LLM-as-a-judge is itself an AI system that can be wrong. Before you rely on its scores, hand-label a small set of about 20–100 cases yourself, then check how often the judge agrees with you. If it disagrees with humans a third of the time, its "pass rate" is measuring the judge, not your app. Treat the judge's rubric as code you test and iterate on.

!!! tip "Make the judge explain before it scores"

    Ask the judge to write its reasoning first and emit the score second. Models are more accurate when they reason before deciding, and the written reason is what lets *you* audit a surprising score instead of trusting a bare number. In pydantic-evals, `LLMJudge` records that reason alongside the score.

## Consequences to know

- **Sending eval results to Logfire stores them.** With `logfire.configure()`, an eval run (inputs, outputs, and scores) is sent to and stored in your Logfire project, visible to your team. Run without it to keep results local.
- **LLM-as-a-judge scorers cost money.** Each judged output is another model call. A 500-case dataset with two LLM judges is 1,000 extra model calls per experiment.

## Next steps

- **[Run an evaluation](datasets/evaluations.md)**: the offline path end to end, with a worked example and a real report.
- **[Datasets](datasets/index.md)**: build and curate the test cases you evaluate against.
- **[Evals SDK](datasets/sdk.md)**: manage datasets and evaluations programmatically.
- **[Evals in the web UI](datasets/ui.md)**: create datasets and compare experiments in Logfire.
- **[Live Evaluations](../guides/web-ui/live-evals.md)**: score real production traffic as it happens.
- **[Human review](human-review.md)**: turn human judgment and user feedback into scores that sit next to your automated ones.
