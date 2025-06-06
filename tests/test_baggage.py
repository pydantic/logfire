from typing import Any

import pytest
from inline_snapshot import snapshot
from opentelemetry import baggage as otel_baggage

import logfire
from logfire.testing import TestExporter


def test_baggage_sets_and_restores():
    assert logfire.get_baggage() == {}
    assert otel_baggage.get_all() == {}
    with logfire.update_baggage({'foo': 'bar'}):
        assert logfire.get_baggage() == {'foo': 'bar'}
        assert otel_baggage.get_all() == {'foo': 'bar'}
        with logfire.update_baggage({'baz': 'qux'}):
            assert logfire.get_baggage() == {'foo': 'bar', 'baz': 'qux'}
            assert otel_baggage.get_all() == {'foo': 'bar', 'baz': 'qux'}
        assert logfire.get_baggage() == {'foo': 'bar'}
        assert otel_baggage.get_all() == {'foo': 'bar'}
    assert logfire.get_baggage() == {}
    assert otel_baggage.get_all() == {}


def test_baggage_overwrites():
    assert logfire.get_baggage() == {}
    assert otel_baggage.get_all() == {}
    with logfire.update_baggage({'n': 1}):
        assert logfire.get_baggage() == {'n': 1}
        assert otel_baggage.get_all() == {'n': 1}
        with logfire.update_baggage({'n': 2}):
            assert logfire.get_baggage() == {'n': 2}
            assert otel_baggage.get_all() == {'n': 2}
        assert logfire.get_baggage() == {'n': 1}
        assert otel_baggage.get_all() == {'n': 1}
    assert logfire.get_baggage() == {}
    assert otel_baggage.get_all() == {}


def test_baggage_does_not_go_to_span_attributes_by_default(config_kwargs: dict[str, Any], exporter: TestExporter):
    logfire.configure(**config_kwargs, add_baggage_to_attributes=False)
    with logfire.update_baggage({'a': 1}):
        with logfire.span('outer', b=2):
            # confirm the behavior of attributes that conflict with baggage:
            with logfire.span('inner', a=2, b=3):
                logfire.info('info')
    assert _get_simplified_spans(exporter)[::-1] == snapshot(
        [
            {'attributes': {'b': 2}, 'name': 'outer'},
            {'attributes': {'a': 2, 'b': 3}, 'name': 'inner'},
            {'attributes': {}, 'name': 'info'},
        ]
    )


@pytest.mark.parametrize(
    'add_baggage_to_attributes,expected',
    [
        (
            True,
            snapshot(
                [
                    {'attributes': {'a': 1}, 'name': 'outer'},
                    {'attributes': {'a': 1, 'b': 2}, 'name': 'outer-middle'},
                    {'attributes': {'a': 3, 'b': 2}, 'name': 'inner-middle'},
                    {'attributes': {'a': 3, 'b': 2}, 'name': 'inner'},
                    {'attributes': {'a': 3, 'b': 2}, 'name': 'info'},
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
                    {'attributes': {'a': 4}, 'name': 'inner'},
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
    # Use the default TailSamplingOptions.level of 'notice'.
    # Set duration to None to not include spans with a long duration.
    logfire.configure(**config_kwargs, add_baggage_to_attributes=add_baggage_to_attributes)
    with logfire.update_baggage({'a': 1}):
        with logfire.span('outer'):
            with logfire.update_baggage({'b': 2}):
                with logfire.span('outer-middle'):
                    with logfire.update_baggage({'a': 3}):
                        with logfire.span('inner-middle'):
                            # confirm the behavior of attributes that conflict with baggage:
                            with logfire.span('inner', a=4):
                                logfire.info('info')

    assert _get_simplified_spans(exporter)[::-1] == expected


def _get_simplified_spans(exporter: TestExporter) -> list[dict[str, Any]]:
    return [
        {
            'name': span['name'],
            'attributes': {
                k: v
                for k, v in span['attributes'].items()
                if not k.startswith('code.') and not k.startswith('logfire.')
            },
        }
        for span in exporter.exported_spans_as_dict()
    ]
