from __future__ import annotations

from typing import Any

from opentelemetry import context as otel_context
from opentelemetry.trace import Span, set_span_in_context
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

import logfire
from logfire._internal.constants import ATTRIBUTES_MESSAGE_KEY, ATTRIBUTES_SPAN_TYPE_KEY, DISABLE_CONSOLE_KEY

# from logfire.propagate import attach_context

TRACEPARENT_PROPAGATOR = TraceContextTextMapPropagator()
TRACEPARENT_NAME = 'traceparent'
assert TRACEPARENT_NAME in TRACEPARENT_PROPAGATOR.fields

feedback_logfire = logfire.with_settings(custom_scope_suffix='feedback')


def get_traceparent(span: Span | logfire.LogfireSpan) -> str:
    """TODO."""
    real_span: Span
    if isinstance(span, Span):
        real_span = span
    else:
        real_span = span._span  # type: ignore
        assert real_span
    context = set_span_in_context(real_span)
    carrier: dict[str, Any] = {}
    TRACEPARENT_PROPAGATOR.inject(carrier, context)
    return carrier.get(TRACEPARENT_NAME, '')


def raw_annotate_span(traceparent: str, span_name: str, message: str, attributes: dict[str, Any]) -> None:
    """TODO."""
    old_context = otel_context.get_current()
    # with attach_context({TRACEPARENT_NAME: traceparent}, propagator=TRACEPARENT_PROPAGATOR):
    new_context = TRACEPARENT_PROPAGATOR.extract(carrier={TRACEPARENT_NAME: traceparent})
    try:
        otel_context.attach(new_context)
        feedback_logfire.info(
            span_name,
            **attributes,  # type: ignore
            **{
                ATTRIBUTES_MESSAGE_KEY: message,
                ATTRIBUTES_SPAN_TYPE_KEY: 'annotation',
                DISABLE_CONSOLE_KEY: True,
            },
        )
    finally:
        otel_context.attach(old_context)


def record_feedback(
    traceparent: str,
    name: str,
    value: int | float | bool | str,
    comment: str | None = None,
    extra_attributes: dict[str, Any] | None = None,
) -> None:
    """Evaluate a span with a given value and reason.

    Args:
        traceparent: The traceparent string.
        name: The name of the evaluation.
        value: The value of the evaluation.
            Numbers are interpreted as scores, strings as labels, and booleans as assertions.
        comment: An optional reason for the evaluation.
        extra_attributes: Optional additional attributes to include in the span.
    """
    attributes: dict[str, Any] = {'feedback.name': name}

    if isinstance(value, bool):
        attributes['feedback.assertion'] = value
    elif isinstance(value, (int, float)):
        attributes['feedback.score'] = value
    else:
        assert isinstance(value, str), f'Value must be a string, int, float, or bool, not {type(value)}'
        attributes['feedback.label'] = value

    if comment:
        attributes['feedback.comment'] = comment

    if extra_attributes:
        attributes.update(extra_attributes)

    raw_annotate_span(traceparent, 'feedback', f'feedback: {name}={value}', attributes)


def main():
    """TODO."""
    logfire.configure(
        console=logfire.ConsoleOptions(verbose=True),
        advanced=logfire.AdvancedOptions(base_url='http://localhost:8000'),
        token='test-e2e-write-token',
    )

    with logfire.span('mock agent run') as span:
        agent_run_traceparent = get_traceparent(span)

    record_feedback(
        agent_run_traceparent,
        'factuality',
        0.1,
        comment='the mock agent lied',
        extra_attributes={'agent_name': 'mock'},
    )


main()
