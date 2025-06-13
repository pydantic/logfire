from typing import Any, Literal

import pytest
from inline_snapshot import snapshot
from inline_snapshot.extra import warns
from opentelemetry import baggage as otel_baggage

import logfire
from logfire.testing import TestExporter


def test_baggage_sets_and_restores():
    assert logfire.get_baggage() == {}
    assert otel_baggage.get_all() == {}
    with logfire.set_baggage(foo='bar'):
        assert logfire.get_baggage() == {'foo': 'bar'}
        assert otel_baggage.get_all() == {'foo': 'bar'}
        with logfire.set_baggage(baz='qux'):
            assert logfire.get_baggage() == {'foo': 'bar', 'baz': 'qux'}
            assert otel_baggage.get_all() == {'foo': 'bar', 'baz': 'qux'}
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
                    'UserWarning: Baggage value for key "a" is a BadRepr. Converting to string.',
                ),
                (
                    __file__,
                    'UserWarning: Baggage value for key "b" is a list. Converting to string.',
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
                    {'attributes': {'a': '4', 'b': '2'}, 'name': 'inner'},
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
                    {'attributes': {}, 'name': 'inner-middle'},
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
    add_baggage_to_attributes: Literal[False, True, 'json'],
    expected: list[dict[str, Any]],
):
    config_kwargs['add_baggage_to_attributes'] = add_baggage_to_attributes
    logfire.configure(**config_kwargs)
    with logfire.set_baggage(a='1'):
        with logfire.span('outer'):
            with logfire.set_baggage(b='2'):
                with logfire.span('outer-middle'):
                    with logfire.set_baggage(a='3'):
                        with logfire.span('inner-middle'):
                            # confirm the behavior of attributes that conflict with baggage:
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
