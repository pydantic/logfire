from __future__ import annotations

from typing import Any

from opentelemetry.trace import Span, set_span_in_context
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

import logfire
from logfire._internal.constants import ATTRIBUTES_MESSAGE_KEY, ATTRIBUTES_SPAN_TYPE_KEY
from logfire.propagate import attach_context

TRACEPARENT_PROPAGATOR = TraceContextTextMapPropagator()
TRACEPARENT_NAME = 'traceparent'
assert TRACEPARENT_NAME in TRACEPARENT_PROPAGATOR.fields

feedback_logfire = logfire.with_settings(custom_scope_suffix='feedback')


def get_traceparent(span: Span | logfire.LogfireSpan) -> str:
    """Get a string representing the span context to use for annotating spans."""
    real_span: Span
    if isinstance(span, Span):
        real_span = span
    else:
        real_span = span._span  # pyright: ignore[reportAssignmentType, reportPrivateUsage]
        assert real_span
    context = set_span_in_context(real_span)
    carrier: dict[str, Any] = {}
    TRACEPARENT_PROPAGATOR.inject(carrier, context)
    return carrier.get(TRACEPARENT_NAME, '')


def raw_annotate_span(traceparent: str, span_name: str, message: str, attributes: dict[str, Any]) -> None:
    """Create a span of kind 'annotation' as a child of the span with the given traceparent."""
    with attach_context({TRACEPARENT_NAME: traceparent}, propagator=TRACEPARENT_PROPAGATOR):
        feedback_logfire.info(
            span_name,
            **attributes,  # pyright: ignore[reportArgumentType]
            **{
                ATTRIBUTES_MESSAGE_KEY: message,
                ATTRIBUTES_SPAN_TYPE_KEY: 'annotation',
            },
        )


def record_feedback(
    traceparent: str,
    name: str,
    value: int | float | bool | str,
    comment: str | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    """Attach feedback to a span.

    This is a more structured version of `raw_annotate_span`
    with special attributes recognized by the Logfire UI.

    Args:
        traceparent: The traceparent string.
        name: The name of the evaluation.
        value: The value of the evaluation.
            Numbers are interpreted as scores, strings as labels, and booleans as assertions.
        comment: An optional reason for the evaluation.
        extra: Optional additional attributes to include in the span.
    """
    attributes: dict[str, Any] = {'logfire.feedback.name': name, name: value}

    if extra:
        assert name not in extra  # TODO check better
        attributes.update(extra)

    if comment:
        attributes['logfire.feedback.comment'] = comment

    raw_annotate_span(
        traceparent,
        f'feedback: {name}',
        f'feedback: {name} = {value!r}',
        attributes,
    )


def record_score(
    traceparent: str,
    name: str,
    value: int | float | bool | None = None,
    *,
    target: str,
    label: str | None = None,
    explanation: str | None = None,
    agent_name: str | None = None,
    evaluator_version: str | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    """Record an evaluation result for a span, including after the span has ended.

    Emits a `gen_ai.evaluation.result` log using OpenTelemetry evaluation attributes.
    Unlike `record_feedback`, this records a score rather than a feedback annotation.

    Args:
        traceparent: The traceparent string returned by `get_traceparent` for the evaluated span.
        name: The name of the evaluation.
        value: An optional numeric score. Booleans become 1.0 or 0.0 and default the label to 'pass' or 'fail'.
        target: The evaluation target, typically the name of the evaluated agent.
        label: An optional score label, overriding the default for boolean values.
        explanation: An optional explanation of the result.
        agent_name: The agent name, defaulting to `target`.
        evaluator_version: An optional version of the evaluator.
        extra: Additional attributes. Explicit evaluation arguments take precedence over these attributes.
    """
    attributes = dict(extra or {})
    attributes.pop(ATTRIBUTES_SPAN_TYPE_KEY, None)
    attributes.update(
        {
            'gen_ai.evaluation.name': name,
            'gen_ai.evaluation.target': target,
            'gen_ai.agent.name': target if agent_name is None else agent_name,
        }
    )
    if isinstance(value, bool):
        if label is None:
            label = 'pass' if value else 'fail'
        value = float(value)
    if value is not None:
        attributes['gen_ai.evaluation.score.value'] = value
    if label is not None:
        attributes['gen_ai.evaluation.score.label'] = label
    if explanation is not None:
        attributes['gen_ai.evaluation.explanation'] = explanation
    if evaluator_version is not None:
        attributes['gen_ai.evaluation.evaluator.version'] = evaluator_version

    with attach_context({TRACEPARENT_NAME: traceparent}, propagator=TRACEPARENT_PROPAGATOR):
        feedback_logfire.log('info', 'gen_ai.evaluation.result', attributes)
