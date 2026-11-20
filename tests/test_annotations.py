import pytest
from inline_snapshot import snapshot
from opentelemetry.trace import get_current_span

import logfire
from logfire._internal.exporters.test import TestExporter
from logfire.experimental.annotations import get_traceparent, raw_annotate_span, record_feedback, record_score


def test_record_score_event(exporter: TestExporter):
    with logfire.span('agent run') as span:
        traceparent = get_traceparent(span)

    record_score(
        traceparent,
        name='human_review',
        value=1.0,
        explanation='Sent as drafted',
        target='support_agent',
    )

    records = exporter.exported_spans_as_dict(parse_json_attributes=True)
    assert len(records) == 2
    result = records[-1]
    assert result['parent'] == {'trace_id': 1, 'span_id': 1, 'is_remote': True}
    assert result['name'] == 'gen_ai.evaluation.result'
    assert result['attributes']['logfire.span_type'] == 'log'
    assert {key: value for key, value in result['attributes'].items() if key.startswith('gen_ai.')} == snapshot(
        {
            'gen_ai.evaluation.name': 'human_review',
            'gen_ai.evaluation.score.value': 1.0,
            'gen_ai.evaluation.explanation': 'Sent as drafted',
            'gen_ai.evaluation.target': 'support_agent',
            'gen_ai.agent.name': 'support_agent',
        }
    )


@pytest.mark.parametrize(
    'value, label, expected',
    [
        (True, None, {'gen_ai.evaluation.score.value': 1.0, 'gen_ai.evaluation.score.label': 'pass'}),
        (False, None, {'gen_ai.evaluation.score.value': 0.0, 'gen_ai.evaluation.score.label': 'fail'}),
        (False, 'rejected', {'gen_ai.evaluation.score.value': 0.0, 'gen_ai.evaluation.score.label': 'rejected'}),
        (0, None, {'gen_ai.evaluation.score.value': 0}),
        (-0.5, '', {'gen_ai.evaluation.score.value': -0.5, 'gen_ai.evaluation.score.label': ''}),
        (None, 'approved', {'gen_ai.evaluation.score.label': 'approved'}),
        (None, None, {}),
    ],
)
def test_record_score_values(
    exporter: TestExporter, value: float | bool | None, label: str | None, expected: dict[str, float | str]
):
    with logfire.span('agent run') as span:
        traceparent = get_traceparent(span)

    record_score(traceparent, 'review', value, target='agent', label=label)

    attributes = exporter.exported_spans_as_dict()[-1]['attributes']
    assert {key: value for key, value in attributes.items() if key.startswith('gen_ai.evaluation.score.')} == expected
    assert 'gen_ai.evaluation.explanation' not in attributes
    assert 'gen_ai.evaluation.evaluator.version' not in attributes
    if isinstance(value, bool):
        assert type(attributes['gen_ai.evaluation.score.value']) is float


def test_record_score_context_and_extra(exporter: TestExporter):
    with logfire.span('agent run') as span:
        traceparent = get_traceparent(span)

    extra = {'reviewer': {'id': 42}, 'gen_ai.evaluation.name': 'ignored', 'logfire.msg': 'reviewed'}
    with logfire.span('review request') as current:
        current_traceparent = get_traceparent(current)
        for _ in range(2):
            record_score(
                traceparent,
                'review',
                True,
                target='support',
                agent_name='support_agent',
                explanation='',
                evaluator_version='v1',
                extra=extra,
            )
            assert get_traceparent(get_current_span()) == current_traceparent

    assert extra == {'reviewer': {'id': 42}, 'gen_ai.evaluation.name': 'ignored', 'logfire.msg': 'reviewed'}
    records = exporter.exported_spans_as_dict(parse_json_attributes=True)
    results = [record for record in records if record['name'] == 'gen_ai.evaluation.result']
    assert len(results) == 2
    for result in results:
        assert result['parent'] == {'trace_id': 1, 'span_id': 1, 'is_remote': True}
        assert {key: value for key, value in result['attributes'].items() if key.startswith('gen_ai.')} == snapshot(
            {
                'gen_ai.evaluation.name': 'review',
                'gen_ai.evaluation.target': 'support',
                'gen_ai.agent.name': 'support_agent',
                'gen_ai.evaluation.score.value': 1.0,
                'gen_ai.evaluation.score.label': 'pass',
                'gen_ai.evaluation.explanation': '',
                'gen_ai.evaluation.evaluator.version': 'v1',
            }
        )
        assert result['attributes']['reviewer'] == {'id': 42}


def test_get_traceparent(exporter: TestExporter):
    with logfire.span('hi') as span:
        traceparent = get_traceparent(span)
        assert (
            traceparent
            == get_traceparent(get_current_span())
            == snapshot('00-00000000000000000000000000000001-0000000000000001-01')
        )

    raw_annotate_span(traceparent, 'my_span_name', 'my_message', {'key': 'value'})

    record_feedback(
        traceparent,
        'factuality',
        0.1,
        comment='the mock agent lied',
        extra={'agent_name': 'mock'},
    )

    record_feedback(
        traceparent,
        'rudeness',
        'very',
    )

    assert exporter.exported_spans_as_dict(_include_pending_spans=True) == snapshot(
        [
            {
                'name': 'hi',
                'context': {'trace_id': 1, 'span_id': 2, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 1000000000,
                'end_time': 1000000000,
                'attributes': {
                    'code.filepath': 'test_annotations.py',
                    'code.function': 'test_get_traceparent',
                    'code.lineno': 123,
                    'logfire.msg_template': 'hi',
                    'logfire.msg': 'hi',
                    'logfire.span_type': 'pending_span',
                    'logfire.pending_parent_id': '0000000000000000',
                },
            },
            {
                'name': 'hi',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 2000000000,
                'attributes': {
                    'code.filepath': 'test_annotations.py',
                    'code.function': 'test_get_traceparent',
                    'code.lineno': 123,
                    'logfire.msg_template': 'hi',
                    'logfire.msg': 'hi',
                    'logfire.span_type': 'span',
                },
            },
            {
                'name': 'my_span_name',
                'context': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': True},
                'start_time': 3000000000,
                'end_time': 3000000000,
                'attributes': {
                    'logfire.span_type': 'annotation',
                    'logfire.level_num': 9,
                    'logfire.msg_template': 'my_span_name',
                    'logfire.msg': 'my_message',
                    'code.filepath': 'test_annotations.py',
                    'code.function': 'test_get_traceparent',
                    'code.lineno': 123,
                    'key': 'value',
                    'logfire.json_schema': '{"type":"object","properties":{"key":{},"logfire.span_type":{}}}',
                },
            },
            {
                'name': 'feedback: factuality',
                'context': {'trace_id': 1, 'span_id': 4, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': True},
                'start_time': 4000000000,
                'end_time': 4000000000,
                'attributes': {
                    'logfire.span_type': 'annotation',
                    'logfire.level_num': 9,
                    'logfire.msg_template': 'feedback: factuality',
                    'logfire.msg': 'feedback: factuality = 0.1',
                    'code.filepath': 'test_annotations.py',
                    'code.function': 'test_get_traceparent',
                    'code.lineno': 123,
                    'logfire.feedback.name': 'factuality',
                    'factuality': 0.1,
                    'logfire.feedback.comment': 'the mock agent lied',
                    'agent_name': 'mock',
                    'logfire.json_schema': '{"type":"object","properties":{"logfire.feedback.name":{},"factuality":{},"agent_name":{},"logfire.feedback.comment":{},"logfire.span_type":{}}}',
                },
            },
            {
                'name': 'feedback: rudeness',
                'context': {'trace_id': 1, 'span_id': 5, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': True},
                'start_time': 5000000000,
                'end_time': 5000000000,
                'attributes': {
                    'logfire.span_type': 'annotation',
                    'logfire.level_num': 9,
                    'logfire.msg_template': 'feedback: rudeness',
                    'logfire.msg': "feedback: rudeness = 'very'",
                    'code.filepath': 'test_annotations.py',
                    'code.function': 'test_get_traceparent',
                    'code.lineno': 123,
                    'logfire.feedback.name': 'rudeness',
                    'rudeness': 'very',
                    'logfire.json_schema': '{"type":"object","properties":{"logfire.feedback.name":{},"rudeness":{},"logfire.span_type":{}}}',
                },
            },
        ]
    )
