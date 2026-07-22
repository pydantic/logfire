---
title: "Human review: score AI outputs by hand"
description: "Add human judgment to your AI evaluations in Pydantic Logfire: annotate spans and runs, work an annotation queue, and capture user feedback as scores."
---

# Human review

Some questions about an AI's output can't be answered by code or by another model: was this support reply actually helpful? was the tone right? did the agent do the sensible thing? **Human review** is how a person looks at a real interaction and records a judgment. That judgment lands as a **score** (one saved quality rating for an output), the same kind of score your automated evaluations produce, so human ratings sit next to code and LLM-as-a-judge ratings on the same output and roll up into the same numbers.

If you're new to scores and evaluations, read the [evals overview](overview.md) first. This page assumes those terms.

## When you'd do this

- You need a ground-truth label a machine can't produce: "was this answer genuinely helpful?"
- You're building the ~20–100 hand-labeled cases you need to [benchmark an LLM judge](overview.md#best-practices-with-the-reason-attached) before trusting it.
- You want to curate real production interactions into a [dataset](datasets/index.md) of good and bad examples.
- You want to hear directly from your end users: a thumbs-up/down on an answer, in your own product.

## Three ways to do one job

Human review shows up in three places in Logfire. They differ in *who* does the reviewing and *how* the work is dispatched, but all three produce the same thing: **scores attached to an output**.

### Annotate a span or a run

The most direct form: open a **span** (one unit of work: a single operation, with a name, a start, and a duration) or a whole **run** in the [live view](../guides/web-ui/live.md), and record your judgment on it directly: a pass/fail flag, a label, a numeric rating, or a free-text note. Reach for this when you're already looking at a trace and want to capture what you see.

- **Span annotation**: rate a single operation: this one LLM call, this one tool call.
- **Run annotation** (Beta): rate a whole run of your AI (an end-to-end agent invocation across many spans) as one unit, rather than a single span inside it. Enable it with the `run_annotations` feature flag.

!!! note "Run annotations are in Beta"

    Run-level annotations are behind the `run_annotations` feature flag and may change. Span annotations are generally available.

### Work an annotation queue

When review needs to be systematic rather than opportunistic (a reviewer sitting down to label 100 interactions in a row), an **annotation queue** is a curated list of interactions lined up for review, so a reviewer works through them one after another instead of hunting for traces to rate. Fill a queue from production traffic (for example, every low-scoring call, or a random sample), then a human works down the list, and each judgment is saved as a score on that interaction.

!!! note "Annotation queues are a Design Partner feature"

    Annotation queues are available to Design Partner customers (teams on our early-access program).

### Capture user feedback

The reviewer doesn't have to be on your team: it can be your end user. Capture a signal from inside your own product (a thumbs-up/down, a star rating, a "this didn't help" click) and attach it to the interaction that produced it. That feedback is stored as a score on the same output, so real-user judgment sits alongside your internal reviews and your automated scorers.

Attach feedback to a span with `record_feedback`. When you handle the request, save the span's **traceparent** (a short string that identifies the span); later, when the user reacts, reference it to record their rating:

```python
import logfire
from logfire.experimental.annotations import get_traceparent, record_feedback

logfire.configure()

with logfire.span('answer question') as span:
    traceparent = get_traceparent(span)  # save this alongside the response you return
    ...  # produce the answer

# later, when the user reacts in your product:
record_feedback(
    traceparent,
    'helpful',  # the name of the feedback
    True,  # the type sets the score's shape: bool = pass/fail, number = numeric, string = label
    comment='User clicked thumbs up',
)
```

The value's type sets the score's **shape** (a **bool** records a pass/fail, a **string** records a label, a **number** records a numeric rating) and any `comment` is saved as the reason. Open that trace in the Live view and you'll see the `helpful` score on the span, next to any scores from your automated evaluators.

!!! note "Experimental API"

    `record_feedback` and `get_traceparent` live in `logfire.experimental.annotations`; the interface may change in a future release.

## Why these feed your evals

Because all three produce scores, human review isn't a separate island:

- **Ground truth for judges.** Hand-labeled scores are what you [benchmark an LLM judge against](overview.md#best-practices-with-the-reason-attached). If the judge disagrees with your humans a third of the time, you know its automated scores aren't trustworthy yet.
- **Seeds for datasets.** An interaction a human flagged as bad is exactly the case you want in your [dataset](datasets/index.md), so your offline evals re-test it on every future version.
- **One picture of quality.** On any given output, you can see the code scorer, the LLM judge, the human reviewer, and the end user's feedback together, not four disconnected tools.

## Consequences to know

- **Annotations and feedback are stored in Logfire.** A score you record (and any free-text note attached to it) is sent to and stored in your Logfire project, visible to your team.
- **User feedback carries whatever you attach.** If you send free-text feedback from your product, treat it like any other user data: it may contain personally identifiable information (PII), so [redact sensitive data](../how-to-guides/scrubbing.md) before it leaves your machine if that's a concern.

## Next steps

- [Evals overview](overview.md): how scores, scorers, and experiments fit together.
- [Datasets](datasets/index.md): turn the interactions you reviewed into re-runnable test cases.
- [Run an evaluation](datasets/evaluations.md): score a whole dataset offline.
- [Live Evaluations](../guides/web-ui/live-evals.md): score production traffic automatically, then send the uncertain cases to human review.
