---
title: "Annotations: review and label your agent runs"
description: "Annotations let you label individual agent runs in Logfire with a verdict, a category, the answer the agent should have given, a comment, and tags, then triage them across agents and export them as eval cases."
---

# Annotations

!!! note "Beta: feedback welcome"
    Annotations are in beta and shipping fixes and improvements quickly. Tell us what's missing or broken in the [Logfire Slack community](../../../join-slack/index.html) or email [support@pydantic.dev](mailto:support@pydantic.dev).

Review the output of your AI agents and label each run with a verdict (pass, neutral, or fail), a category, the answer it should have given, and a comment, without leaving Logfire. An *agent run* is one execution of an agent, recorded as a trace (the full journey of one request). The label you attach is an *annotation*.

## Why you'd use it

Teams running AI agents in production review the agent's output by hand: to triage a regression, to spot-check a sample after a prompt change, or to seed an [evaluation](../../../guides/web-ui/evals.md) (a repeatable test of output quality). Doing that review outside Logfire loses the thread. The run gets screenshotted into a doc, the verdict is typed into a spreadsheet, and the corrected answer is stuck in a comment that nobody can promote to a test case later. When span retention rolls the trace off after 30 days, the verdict goes with it.

Annotations keep the judgment next to the run. They live in their own store, so they stay editable, can be removed, and are retained past the 30-day span retention, even after the underlying trace ages out. They give you two things a spreadsheet can't:

- a **shared record** of what has been reviewed, so two reviewers don't double-check the same run, and
- a **corrected answer** on each failing run that exports straight into an eval [dataset](../../../evaluate/datasets/index.md) (a collection of test cases you evaluate against).

When *not* to use it: annotations are for human review of past runs. To score live production traffic automatically as it arrives, use [live evals](../../../guides/web-ui/live-evals.md) instead.

You'll find **Annotations** in the project sidebar under **AI Evaluations**.

## Annotate a run

1. Open **Agents** in the sidebar and click into an agent.
2. On the **Runs** tab, click a row to expand it, then click **Annotate** in the run detail header. A sidebar opens on the right.
3. Set a verdict. Click **Pass**, **Neutral**, or **Fail**, or press `1`, `2`, or `3`.
4. Add any of the optional fields below. Which ones appear depends on the verdict you picked.
5. Save. Press `cmd+enter` (`ctrl+enter` on Windows and Linux) to save and move to the next unannotated run, or click **Save**.

As you save, the **X / Y annotated** badge at the top of the runs table updates, so you can see how far through a batch you are.

## What you can record

An annotation can hold:

- **Verdict**: `pass`, `neutral`, or `fail`. This is the headline label, shown as a colored icon next to the run afterwards. The other fields are optional context, and you can save an annotation with just a comment or a tag if you prefer.
- **Category** (for neutral or failing runs): a short label for the *kind* of result, for example `hallucination` or `wrong-tool`. Use a consistent set so you can group by it later.
- **Expected output** (for failing runs): the answer the agent should have given. This is the field that turns a failing run into a reusable eval case, so it's worth writing out in full.
- **Comment**: free-text notes for the next reviewer.
- **Tags**: extra labels for filtering.

## Review across agents

Click **Annotations** in the sidebar for a project-wide view with two sections:

- **Agents**: a grid of the agents seen in the last 7 days. Click a card to jump straight into that agent's runs with the Annotate sidebar already open.
- **Recent annotations**: a feed of the latest saved annotations, each showing the agent, the reviewer, the category and tags, the comment, and when it was saved.

Use the **Pass / Neutral / Fail** chips and the annotator chips at the top to filter the feed. The chip strip stays pinned as you scroll.

## Export annotations as eval cases

On an agent's detail page, the runs table has an export button next to its annotation filters. It downloads a JSON Lines file (one JSON object per line) of the saved annotations, honoring the runs table's verdict, category, and tag filters, with each run's reviewer and `expected_output` included. Feed that file into an eval [dataset](../../../evaluate/datasets/index.md) to turn the runs your team marked `fail` into the next round of test cases.

## Verify

- **Annotations** appears in the sidebar under **AI Evaluations** with a `Beta` badge.
- After you save a verdict, the run shows a colored verdict icon in the runs table and the **X / Y annotated** count goes up.
- On the **Annotations** page, your annotation shows up in **Recent annotations** within a few seconds, with the agent name resolved and the verdict and reviewer matching what you saved.

## Troubleshooting

- **No agents on the Annotations page.** The grid only lists agents with runs in the last 7 days. If the agent you want is older than that, open it directly from the **Agents** page.
- **The run has no Annotate button.** Annotations attach to agent runs. Make sure you're on the **Runs** tab of an agent detail page and have expanded a run row; the button is in the expanded run's header.
- **The export file is empty.** Export only includes saved annotations, and it honors the runs table's verdict, category, and tag filters. Clear those filters, or set them to match annotations you've saved, then export again.

## Next steps

- Turn your `fail`-labelled runs into a test suite: [Datasets and experiments](../../../evaluate/datasets/index.md).
- Score live traffic automatically instead of by hand: [Live evals](../../../guides/web-ui/live-evals.md).
