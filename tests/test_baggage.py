from typing import Any

import pytest
from inline_snapshot import snapshot
from inline_snapshot.extra import warns
from opentelemetry import baggage as otel_baggage, context

import logfire
from logfire.testing import TestExporter


def test_baggage_sets_and_restores():
    assert logfire.get_baggage() == {}
    assert otel_baggage.get_all() == {}
    with logfire.set_baggage(foo='bar'):
        assert logfire.get_baggage() == {'foo': 'bar'}
        assert otel_baggage.get_all() == {'foo': 'bar'}
        with logfire.set_baggage(baz='3'):
            assert logfire.get_baggage() == {'foo': 'bar', 'baz': '3'}
            assert otel_baggage.get_all() == {'foo': 'bar', 'baz': '3'}
        assert logfire.get_baggage() == {'foo': 'bar'}
        assert otel_baggage.get_all() == {'foo': 'bar'}
    assert logfire.get_baggage() == {}
    assert otel_baggage.get_all() == {}


def test_baggage_overwrites():
    assert logfire.get_baggage() == {}
    assert otel_baggage.get_all() == {}
    with logfire.set_baggage(n='1'):
        assert logfire.get_baggage() == {'n': '1'}
        assert otel_baggage.get_all() == {'n': '1'}
        with logfire.set_baggage(n='2'):
            assert logfire.get_baggage() == {'n': '2'}
            assert otel_baggage.get_all() == {'n': '2'}
        assert logfire.get_baggage() == {'n': '1'}
        assert otel_baggage.get_all() == {'n': '1'}
    assert logfire.get_baggage() == {}
    assert otel_baggage.get_all() == {}


class BadRepr:
    def __repr__(self):
        raise ValueError('bad repr')


def test_set_baggage_non_string():
    with warns(
        snapshot(
            [
                (
                    __file__,
                    'UserWarning: Baggage value for key "a" is of type "BadRepr". Converting to string.',
                ),
                (
                    __file__,
                    'UserWarning: Baggage value for key "b" is of type "list". Converting to string.',
                ),
            ]
        ),
        include_file=True,
    ):
        with logfire.set_baggage(a=BadRepr(), b=[{'c': 'd'}]):  # type: ignore
            assert (
                logfire.get_baggage()
                == otel_baggage.get_all()
                == snapshot({'a': '"<BadRepr object>"', 'b': '[{"c":"d"}]'})
            )


def test_set_baggage_long_string():
    with warns(
        snapshot(
            [
                (
                    __file__,
                    'UserWarning: Baggage value for key "a" is too long. Truncating to 1000 characters.',
                )
            ]
        ),
        include_file=True,
    ):
        with logfire.set_baggage(a='b' * 2000):
            assert (
                logfire.get_baggage()
                == otel_baggage.get_all()
                == snapshot(
                    {
                        'a': 'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb...bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb'
                    }
                )
            )


@pytest.mark.parametrize(
    'add_baggage_to_attributes,expected',
    [
        (
            True,
            snapshot(
                [
                    {'attributes': {'a': '1'}, 'name': 'outer'},
                    {'attributes': {'a': '1', 'b': '2'}, 'name': 'outer-middle'},
                    {'attributes': {'a': '3', 'b': '2'}, 'name': 'inner-middle'},
                    {'attributes': {'a': '4', 'baggage_conflict.a': '3', 'b': '2'}, 'name': 'inner'},
                    {'attributes': {'a': '3', 'b': '2'}, 'name': 'info'},
                ]
            ),
        ),
        (
            False,
            snapshot(
                [
                    {'attributes': {}, 'name': 'outer'},
                    {'attributes': {}, 'name': 'outer-middle'},
                    {'attributes': {'a': '3'}, 'name': 'inner-middle'},
                    {'attributes': {'a': '4'}, 'name': 'inner'},
                    {'attributes': {}, 'name': 'info'},
                ]
            ),
        ),
    ],
)
def test_baggage_goes_to_span_attributes(
    config_kwargs: dict[str, Any],
    exporter: TestExporter,
    add_baggage_to_attributes: bool,
    expected: list[dict[str, Any]],
):
    config_kwargs['add_baggage_to_attributes'] = add_baggage_to_attributes
    logfire.configure(**config_kwargs)
    with logfire.set_baggage(a='1'):
        with logfire.span('outer'):
            with logfire.set_baggage(b='2'):
                with logfire.span('outer-middle'):
                    with logfire.set_baggage(a='3'):
                        # attribute with the same key and same value, nothing happens:
                        with logfire.span('inner-middle', a='3'):
                            # attribute with the same key but different value, baggage key gets renamed:
                            with logfire.span('inner', a='4'):
                                logfire.info('info')

    assert _get_simplified_spans(exporter)[::-1] == expected


def _get_simplified_spans(exporter: TestExporter) -> list[dict[str, Any]]:
    return [
        {
            'name': span['name'],
            'attributes': {
                k: v
                for k, v in span['attributes'].items()
                if not k.startswith(('code.', 'logfire.')) or k == 'logfire.baggage'
            },
        }
        for span in exporter.exported_spans_as_dict()
    ]


def test_baggage_scrubbed(config_kwargs: dict[str, Any], exporter: TestExporter):
    config_kwargs['add_baggage_to_attributes'] = True
    logfire.configure(**config_kwargs)
    with logfire.set_baggage(a='3', secret='foo', bar='my_password'):
        with logfire.span('span'):
            pass

    assert exporter.exported_spans_as_dict(parse_json_attributes=True, _include_pending_spans=True) == snapshot(
        [
            {
                'name': 'span',
                'context': {'trace_id': 1, 'span_id': 2, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 1000000000,
                'end_time': 1000000000,
                'attributes': {
                    'code.filepath': 'test_baggage.py',
                    'code.function': 'test_baggage_scrubbed',
                    'code.lineno': 123,
                    'logfire.msg_template': 'span',
                    'logfire.msg': 'span',
                    'logfire.span_type': 'pending_span',
                    'a': '3',
                    'secret': "[Scrubbed due to 'secret']",
                    'bar': "[Scrubbed due to 'password']",
                    'logfire.pending_parent_id': '0000000000000000',
                    'logfire.scrubbed': [
                        {'path': ['attributes', 'secret'], 'matched_substring': 'secret'},
                        {'path': ['attributes', 'bar'], 'matched_substring': 'password'},
                    ],
                },
            },
            {
                'name': 'span',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 2000000000,
                'attributes': {
                    'code.filepath': 'test_baggage.py',
                    'code.function': 'test_baggage_scrubbed',
                    'code.lineno': 123,
                    'logfire.msg_template': 'span',
                    'logfire.msg': 'span',
                    'logfire.span_type': 'span',
                    'a': '3',
                    'secret': "[Scrubbed due to 'secret']",
                    'bar': "[Scrubbed due to 'password']",
                    'logfire.scrubbed': [
                        {'path': ['attributes', 'secret'], 'matched_substring': 'secret'},
                        {'path': ['attributes', 'bar'], 'matched_substring': 'password'},
                    ],
                },
            },
        ]
    )


def test_raw_baggage_non_string_attribute(config_kwargs: dict[str, Any], exporter: TestExporter):
    config_kwargs['add_baggage_to_attributes'] = True
    logfire.configure(**config_kwargs)
    current_context = otel_baggage.set_baggage('a', 'b')
    current_context = otel_baggage.set_baggage('c', 2, current_context)
    current_context = otel_baggage.set_baggage('d', 'e' * 2000, current_context)
    token = context.attach(current_context)
    try:
        with warns(
            snapshot(
                [
                    'UserWarning: Baggage value for key "c" is of type "int", skipping setting as attribute.',
                    'UserWarning: Baggage value for key "d" is too long. Truncating to 1000 characters before setting as attribute.',
                ]
            ),
        ):
            logfire.info('hi')
    finally:
        context.detach(token)

    assert exporter.exported_spans_as_dict(parse_json_attributes=True) == snapshot(
        [
            {
                'name': 'hi',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 1000000000,
                'attributes': {
                    'logfire.span_type': 'log',
                    'logfire.level_num': 9,
                    'logfire.msg_template': 'hi',
                    'logfire.msg': 'hi',
                    'code.filepath': 'test_baggage.py',
                    'code.function': 'test_raw_baggage_non_string_attribute',
                    'code.lineno': 123,
                    'a': 'b',
                    'd': 'eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee...eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee',
                },
            }
        ]
    )
