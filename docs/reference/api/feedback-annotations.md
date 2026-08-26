---
title: "Record feedback on Logfire spans"
description: "Attach scores, labels, assertions, and comments to an existing Logfire span."
---

Use `record_feedback()` to attach structured feedback to a span when the
evaluation happens outside the code that created the span. Feedback values can
be numeric scores, string labels, or boolean assertions.

```python
import logfire
from logfire.experimental.annotations import get_traceparent, record_feedback

logfire.configure()

with logfire.span("answer question") as span:
    traceparent = get_traceparent(span)
    # Run the operation that you want to evaluate here.

record_feedback(
    traceparent,
    "helpfulness",
    True,
    comment="The response answered the question.",
    extra={"review_source": "support-team"},
)
```

The feedback appears in Logfire as an annotation span named
`feedback: helpfulness`, attached to the evaluated span.

!!! note "Experimental API"

    These functions are in `logfire.experimental.annotations` and may change in
    a future release.

::: logfire.experimental.annotations.get_traceparent

::: logfire.experimental.annotations.record_feedback
