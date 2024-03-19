from __future__ import annotations

import importlib.metadata
from typing import Any

import pytest
from dirty_equals import IsInt
from inline_snapshot import snapshot
from opentelemetry.sdk.metrics.export import AggregationTemporality, InMemoryMetricReader
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from pydantic import BaseModel, ConfigDict, ValidationError, field_validator
from pydantic.dataclasses import dataclass as pydantic_dataclass
from pydantic.plugin import SchemaTypePath
from pydantic_core import core_schema

import logfire
from logfire._config import GLOBAL_CONFIG, PydanticPlugin
from logfire.integrations.pydantic_plugin import LogfirePydanticPlugin
from logfire.testing import SeededRandomIdGenerator, TestExporter
from tests.test_metrics import get_collected_metrics


def test_plugin_listed():
    found = True
    entry_points: list[str] = []
    for d in importlib.metadata.distributions():
        for ep in d.entry_points:
            if ep.group == 'pydantic' and ep.value == 'logfire':
                found = True
            entry_points.append(f'group={ep.group} value={ep.value}')
    assert found, 'logfire pydantic plugin not found, entrypoints:' + '\n'.join(entry_points)


def test_check_plugin_installed():
    """Check Pydantic has found the logfire pydantic plugin."""
    from pydantic.plugin import _loader

    assert repr(next(iter(_loader.get_plugins()))) == 'LogfirePydanticPlugin()'


def test_disable_logfire_pydantic_plugin() -> None:
    logfire.configure(
        send_to_logfire=False,
        pydantic_plugin=PydanticPlugin(record='off'),
        metric_readers=[InMemoryMetricReader()],
    )
    plugin = LogfirePydanticPlugin()
    assert plugin.new_schema_validator(
        core_schema.int_schema(), None, SchemaTypePath(module='', name=''), 'BaseModel', None, {}
    ) == (None, None, None)


def test_logfire_pydantic_plugin_settings_record_off() -> None:
    plugin = LogfirePydanticPlugin()
    assert plugin.new_schema_validator(
        core_schema.int_schema(),
        None,
        SchemaTypePath(module='', name=''),
        'BaseModel',
        None,
        {'logfire': {'record': 'off'}},
    ) == (None, None, None)


def test_logfire_pydantic_plugin_settings_record_off_on_model(exporter: TestExporter) -> None:
    class MyModel(BaseModel, plugin_settings={'logfire': {'record': 'off'}}):
        x: int

    MyModel(x=1)

    assert exporter.exported_spans_as_dict(_include_pending_spans=True) == []


def test_pydantic_plugin_settings_record_override_pydantic_plugin_record(exporter: TestExporter) -> None:
    GLOBAL_CONFIG.pydantic_plugin.record = 'all'

    class MyModel(BaseModel, plugin_settings={'logfire': {'record': 'off'}}):
        x: int

    MyModel(x=1)

    assert exporter.exported_spans_as_dict(_include_pending_spans=True) == []


@pytest.mark.parametrize(
    'include,exclude,module,name,expected_to_include',
    (
        # include
        ({'MyModel'}, set(), '', 'MyModel', True),
        ({'MyModel'}, set(), 'test_module', 'MyModel', True),
        ({'MyModel'}, set(), '', 'TestMyModel', True),
        ({'MyModel'}, set(), 'test_module', 'MyModel1', False),
        ({'test_module::MyModel'}, set(), 'test_module', 'MyModel', True),
        ({'test_module::MyModel'}, set(), '', 'MyModel', False),
        ({'test_module::MyModel'}, set(), 'other_module', 'MyModel', False),
        ({'.*test_module.*::MyModel'}, set(), 'my_test_module1', 'MyModel', True),
        ({'.*test_module.*::MyModel[1,2]'}, set(), 'my_test_module1', 'MyModel1', True),
        ({'.*test_module.*::MyModel[1,2]'}, set(), 'my_test_module1', 'MyModel3', False),
        # exclude
        (set(), {'MyModel'}, '', 'MyModel', False),
        (set(), {'MyModel'}, '', 'MyModel1', True),
        (set(), {'.*test_module.*::MyModel'}, 'my_test_module1', 'MyModel', False),
        (set(), {'.*test_module.*::MyModel[1,2]'}, 'my_test_module1', 'MyModel3', True),
        # include & exclude
        ({'MyModel'}, {'MyModel'}, '', 'MyModel', False),
        ({'MyModel'}, {'MyModel1'}, '', 'MyModel', True),
        ({'.*test_module.*::MyModel[1,2,3]'}, {'.*test_module.*::MyModel[1,3]'}, 'my_test_module', 'MyModel2', True),
        ({'.*test_module.*::MyModel[1,2,3]'}, {'.*test_module.*::MyModel[1,3]'}, 'my_test_module', 'MyModel1', False),
    ),
)
def test_logfire_plugin_include_exclude_models(
    include: set[str], exclude: set[str], module: str, name: str, expected_to_include: bool
) -> None:
    logfire.configure(
        send_to_logfire=False,
        pydantic_plugin=PydanticPlugin(record='all', include=include, exclude=exclude),
        metric_readers=[InMemoryMetricReader()],
    )
    plugin = LogfirePydanticPlugin()

    result = plugin.new_schema_validator(
        core_schema.int_schema(), None, SchemaTypePath(module=module, name=name), 'BaseModel', None, {}
    )
    if expected_to_include:
        assert result != (None, None, None)
    else:
        assert result == (None, None, None)


def test_pydantic_plugin_python_record_failure(exporter: TestExporter, metrics_reader: InMemoryMetricReader) -> None:
    class MyModel(BaseModel, plugin_settings={'logfire': {'record': 'failure'}}):
        x: int

    MyModel(x=1)

    with pytest.raises(ValidationError):
        MyModel(x='a')  # type: ignore

    assert exporter.exported_spans_as_dict(_include_pending_spans=True) == snapshot(
        [
            {
                'name': 'Validation on {schema_name} failed',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 1000000000,
                'attributes': {
                    'logfire.span_type': 'log',
                    'logfire.level_name': 'warn',
                    'logfire.level_num': 13,
                    'logfire.msg_template': 'Validation on {schema_name} failed',
                    'logfire.msg': 'Validation on MyModel failed',
                    'code.filepath': 'test_pydantic_plugin.py',
                    'code.function': 'test_pydantic_plugin_python_record_failure',
                    'code.lineno': 123,
                    'schema_name': 'MyModel',
                    'error_count': 1,
                    'errors': '[{"type":"int_parsing","loc":["x"],"msg":"Input should be a valid integer, unable to parse string as an integer","input":"a"}]',
                    'logfire.json_schema': '{"type":"object","properties":{"schema_name":{},"error_count":{},"errors":{"type":"array","items":{"type":"object","properties":{"loc":{"type":"array","x-python-datatype":"tuple"}}}}}}',
                },
            }
        ]
    )

    metrics_collected = get_collected_metrics(metrics_reader)
    assert metrics_collected == snapshot(
        [
            {
                'name': 'mymodel-successful-validation',
                'description': '',
                'unit': '',
                'data': {
                    'data_points': [
                        {
                            'attributes': {},
                            'start_time_unix_nano': IsInt(gt=0),
                            'time_unix_nano': IsInt(gt=0),
                            'value': 1,
                        }
                    ],
                    'aggregation_temporality': AggregationTemporality.DELTA,
                    'is_monotonic': True,
                },
            },
            {
                'name': 'mymodel-failed-validation',
                'description': '',
                'unit': '',
                'data': {
                    'data_points': [
                        {
                            'attributes': {},
                            'start_time_unix_nano': IsInt(gt=0),
                            'time_unix_nano': IsInt(gt=0),
                            'value': 1,
                        }
                    ],
                    'aggregation_temporality': AggregationTemporality.DELTA,
                    'is_monotonic': True,
                },
            },
        ]
    )


def test_pydantic_plugin_metrics(metrics_reader: InMemoryMetricReader) -> None:
    class MyModel(BaseModel, plugin_settings={'logfire': {'record': 'metric'}}):
        x: int

    MyModel(x=1)
    MyModel(x=2)
    MyModel(x=3)

    with pytest.raises(ValidationError):
        MyModel(x='a')  # type: ignore

    with pytest.raises(ValidationError):
        MyModel(x='a')  # type: ignore

    metrics_collected = get_collected_metrics(metrics_reader)
    assert metrics_collected == snapshot(
        [
            {
                'name': 'mymodel-successful-validation',
                'description': '',
                'unit': '',
                'data': {
                    'data_points': [
                        {
                            'attributes': {},
                            'start_time_unix_nano': IsInt(gt=0),
                            'time_unix_nano': IsInt(gt=0),
                            'value': 3,
                        }
                    ],
                    'aggregation_temporality': AggregationTemporality.DELTA,
                    'is_monotonic': True,
                },
            },
            {
                'name': 'mymodel-failed-validation',
                'description': '',
                'unit': '',
                'data': {
                    'data_points': [
                        {
                            'attributes': {},
                            'start_time_unix_nano': IsInt(gt=0),
                            'time_unix_nano': IsInt(gt=0),
                            'value': 2,
                        }
                    ],
                    'aggregation_temporality': AggregationTemporality.DELTA,
                    'is_monotonic': True,
                },
            },
        ]
    )


def test_pydantic_plugin_python_success(exporter: TestExporter, metrics_reader: InMemoryMetricReader) -> None:
    class MyModel(BaseModel, plugin_settings={'logfire': {'record': 'all'}}):
        x: int

    MyModel(x=1)

    assert exporter.exported_spans_as_dict() == snapshot(
        [
            {
                'name': 'pydantic.validate_python',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 2000000000,
                'attributes': {
                    'logfire.span_type': 'span',
                    'logfire.msg_template': 'Pydantic {schema_name} {validation_method}',
                    'logfire.msg': 'Pydantic MyModel validate_python succeeded',
                    'code.filepath': 'pydantic_plugin.py',
                    'code.function': '_on_enter',
                    'code.lineno': 123,
                    'result': '{"x":1}',
                    'logfire.json_schema': '{"type":"object","properties":{"schema_name":{},"validation_method":{},"input_data":{"type":"object"},"success":{},"result":{"type":"object","title":"MyModel","x-python-datatype":"PydanticModel"}}}',
                    'success': True,
                    'input_data': '{"x":1}',
                    'schema_name': 'MyModel',
                    'validation_method': 'validate_python',
                    'logfire.level_num': 9,
                    'logfire.level_name': 'info',
                },
            }
        ]
    )

    metrics_collected = get_collected_metrics(metrics_reader)
    assert metrics_collected == snapshot(
        [
            {
                'name': 'mymodel-successful-validation',
                'description': '',
                'unit': '',
                'data': {
                    'data_points': [
                        {
                            'attributes': {},
                            'start_time_unix_nano': IsInt(gt=0),
                            'time_unix_nano': IsInt(gt=0),
                            'value': 1,
                        }
                    ],
                    'aggregation_temporality': AggregationTemporality.DELTA,
                    'is_monotonic': True,
                },
            }
        ]
    )


def test_pydantic_plugin_python_error_record_failure(
    exporter: TestExporter, metrics_reader: InMemoryMetricReader
) -> None:
    class MyModel(BaseModel, plugin_settings={'logfire': {'record': 'failure'}}):
        x: int

    with pytest.raises(ValidationError):
        MyModel(x='a')  # type: ignore

    with pytest.raises(ValidationError):
        MyModel(x='a')  # type: ignore

    assert exporter.exported_spans_as_dict(_include_pending_spans=True) == snapshot(
        [
            {
                'name': 'Validation on {schema_name} failed',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 1000000000,
                'attributes': {
                    'logfire.span_type': 'log',
                    'logfire.level_name': 'warn',
                    'logfire.level_num': 13,
                    'logfire.msg_template': 'Validation on {schema_name} failed',
                    'logfire.msg': 'Validation on MyModel failed',
                    'code.filepath': 'test_pydantic_plugin.py',
                    'code.function': 'test_pydantic_plugin_python_error_record_failure',
                    'code.lineno': 123,
                    'schema_name': 'MyModel',
                    'error_count': 1,
                    'errors': '[{"type":"int_parsing","loc":["x"],"msg":"Input should be a valid integer, unable to parse string as an integer","input":"a"}]',
                    'logfire.json_schema': '{"type":"object","properties":{"schema_name":{},"error_count":{},"errors":{"type":"array","items":{"type":"object","properties":{"loc":{"type":"array","x-python-datatype":"tuple"}}}}}}',
                },
            },
            {
                'name': 'Validation on {schema_name} failed',
                'context': {'trace_id': 2, 'span_id': 2, 'is_remote': False},
                'parent': None,
                'start_time': 2000000000,
                'end_time': 2000000000,
                'attributes': {
                    'logfire.span_type': 'log',
                    'logfire.level_name': 'warn',
                    'logfire.level_num': 13,
                    'logfire.msg_template': 'Validation on {schema_name} failed',
                    'logfire.msg': 'Validation on MyModel failed',
                    'code.filepath': 'test_pydantic_plugin.py',
                    'code.function': 'test_pydantic_plugin_python_error_record_failure',
                    'code.lineno': 123,
                    'schema_name': 'MyModel',
                    'error_count': 1,
                    'errors': '[{"type":"int_parsing","loc":["x"],"msg":"Input should be a valid integer, unable to parse string as an integer","input":"a"}]',
                    'logfire.json_schema': '{"type":"object","properties":{"schema_name":{},"error_count":{},"errors":{"type":"array","items":{"type":"object","properties":{"loc":{"type":"array","x-python-datatype":"tuple"}}}}}}',
                },
            },
        ]
    )

    metrics_collected = get_collected_metrics(metrics_reader)
    assert metrics_collected == snapshot(
        [
            {
                'name': 'mymodel-failed-validation',
                'description': '',
                'unit': '',
                'data': {
                    'data_points': [
                        {
                            'attributes': {},
                            'start_time_unix_nano': IsInt(gt=0),
                            'time_unix_nano': IsInt(gt=0),
                            'value': 2,
                        }
                    ],
                    'aggregation_temporality': AggregationTemporality.DELTA,
                    'is_monotonic': True,
                },
            }
        ]
    )


def test_pydantic_plugin_python_error(exporter: TestExporter) -> None:
    class MyModel(BaseModel, plugin_settings={'logfire': {'record': 'all'}}):
        x: int

    with pytest.raises(ValidationError):
        MyModel(x='a')  # type: ignore

    assert exporter.exported_spans_as_dict() == snapshot(
        [
            {
                'name': 'pydantic.validate_python',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 2000000000,
                'attributes': {
                    'logfire.span_type': 'span',
                    'logfire.msg_template': 'Pydantic {schema_name} {validation_method}',
                    'logfire.msg': 'Pydantic MyModel validate_python failed',
                    'code.filepath': 'pydantic_plugin.py',
                    'code.function': '_on_enter',
                    'code.lineno': 123,
                    'schema_name': 'MyModel',
                    'error_count': 1,
                    'errors': '[{"type":"int_parsing","loc":["x"],"msg":"Input should be a valid integer, unable to parse string as an integer","input":"a"}]',
                    'logfire.json_schema': '{"type":"object","properties":{"schema_name":{},"validation_method":{},"input_data":{"type":"object"},"success":{},"error_count":{},"errors":{"type":"array","items":{"type":"object","properties":{"loc":{"type":"array","x-python-datatype":"tuple"}}}}}}',
                    'success': False,
                    'validation_method': 'validate_python',
                    'input_data': '{"x":"a"}',
                    'logfire.level_num': 13,
                    'logfire.level_name': 'warn',
                },
            }
        ]
    )


def test_pydantic_plugin_json_success(exporter: TestExporter) -> None:
    class MyModel(BaseModel, plugin_settings={'logfire': {'record': 'all'}}):
        x: int

    MyModel.model_validate_json('{"x":1}')

    assert exporter.exported_spans_as_dict() == snapshot(
        [
            {
                'name': 'pydantic.validate_json',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 2000000000,
                'attributes': {
                    'logfire.span_type': 'span',
                    'logfire.msg_template': 'Pydantic {schema_name} {validation_method}',
                    'logfire.msg': 'Pydantic MyModel validate_json succeeded',
                    'code.filepath': 'pydantic_plugin.py',
                    'code.function': '_on_enter',
                    'code.lineno': 123,
                    'result': '{"x":1}',
                    'logfire.json_schema': '{"type":"object","properties":{"schema_name":{},"validation_method":{},"input_data":{},"success":{},"result":{"type":"object","title":"MyModel","x-python-datatype":"PydanticModel"}}}',
                    'success': True,
                    'input_data': '{"x":1}',
                    'schema_name': 'MyModel',
                    'validation_method': 'validate_json',
                    'logfire.level_num': 9,
                    'logfire.level_name': 'info',
                },
            }
        ]
    )


def test_pydantic_plugin_json_error(exporter: TestExporter) -> None:
    class MyModel(BaseModel, plugin_settings={'logfire': {'record': 'all'}}):
        x: int

    with pytest.raises(ValidationError):
        MyModel.model_validate({'x': 'a'})

    assert exporter.exported_spans_as_dict() == snapshot(
        [
            {
                'name': 'pydantic.validate_python',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 2000000000,
                'attributes': {
                    'logfire.span_type': 'span',
                    'logfire.msg_template': 'Pydantic {schema_name} {validation_method}',
                    'logfire.msg': 'Pydantic MyModel validate_python failed',
                    'code.filepath': 'pydantic_plugin.py',
                    'code.function': '_on_enter',
                    'code.lineno': 123,
                    'schema_name': 'MyModel',
                    'error_count': 1,
                    'errors': '[{"type":"int_parsing","loc":["x"],"msg":"Input should be a valid integer, unable to parse string as an integer","input":"a"}]',
                    'logfire.json_schema': '{"type":"object","properties":{"schema_name":{},"validation_method":{},"input_data":{"type":"object"},"success":{},"error_count":{},"errors":{"type":"array","items":{"type":"object","properties":{"loc":{"type":"array","x-python-datatype":"tuple"}}}}}}',
                    'success': False,
                    'validation_method': 'validate_python',
                    'input_data': '{"x":"a"}',
                    'logfire.level_num': 13,
                    'logfire.level_name': 'warn',
                },
            }
        ]
    )


def test_pydantic_plugin_strings_success(exporter: TestExporter) -> None:
    class MyModel(BaseModel, plugin_settings={'logfire': {'record': 'all'}}):
        x: int

    MyModel.model_validate_strings({'x': '1'}, strict=True)

    assert exporter.exported_spans_as_dict() == snapshot(
        [
            {
                'name': 'pydantic.validate_strings',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 2000000000,
                'attributes': {
                    'logfire.span_type': 'span',
                    'logfire.msg_template': 'Pydantic {schema_name} {validation_method}',
                    'logfire.msg': 'Pydantic MyModel validate_strings succeeded',
                    'code.filepath': 'pydantic_plugin.py',
                    'code.function': '_on_enter',
                    'code.lineno': 123,
                    'result': '{"x":1}',
                    'logfire.json_schema': '{"type":"object","properties":{"schema_name":{},"validation_method":{},"input_data":{"type":"object"},"success":{},"result":{"type":"object","title":"MyModel","x-python-datatype":"PydanticModel"}}}',
                    'success': True,
                    'input_data': '{"x":"1"}',
                    'schema_name': 'MyModel',
                    'validation_method': 'validate_strings',
                    'logfire.level_num': 9,
                    'logfire.level_name': 'info',
                },
            }
        ]
    )


def test_pydantic_plugin_strings_error(exporter: TestExporter) -> None:
    class MyModel(BaseModel, plugin_settings={'logfire': {'record': 'all'}}):
        x: int

    with pytest.raises(ValidationError):
        MyModel.model_validate_strings({'x': 'a'})

    assert exporter.exported_spans_as_dict() == snapshot(
        [
            {
                'name': 'pydantic.validate_strings',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 2000000000,
                'attributes': {
                    'logfire.span_type': 'span',
                    'logfire.msg_template': 'Pydantic {schema_name} {validation_method}',
                    'logfire.msg': 'Pydantic MyModel validate_strings failed',
                    'code.filepath': 'pydantic_plugin.py',
                    'code.function': '_on_enter',
                    'code.lineno': 123,
                    'schema_name': 'MyModel',
                    'error_count': 1,
                    'errors': '[{"type":"int_parsing","loc":["x"],"msg":"Input should be a valid integer, unable to parse string as an integer","input":"a"}]',
                    'logfire.json_schema': '{"type":"object","properties":{"schema_name":{},"validation_method":{},"input_data":{"type":"object"},"success":{},"error_count":{},"errors":{"type":"array","items":{"type":"object","properties":{"loc":{"type":"array","x-python-datatype":"tuple"}}}}}}',
                    'success': False,
                    'validation_method': 'validate_strings',
                    'input_data': '{"x":"a"}',
                    'logfire.level_num': 13,
                    'logfire.level_name': 'warn',
                },
            }
        ]
    )


def test_pydantic_plugin_with_dataclass(exporter: TestExporter) -> None:
    @pydantic_dataclass(config=ConfigDict(plugin_settings={'logfire': {'record': 'failure'}}))
    class MyDataclass:
        x: int

    with pytest.raises(ValidationError):
        MyDataclass(x='a')

    assert exporter.exported_spans_as_dict() == snapshot(
        [
            {
                'name': 'Validation on {schema_name} failed',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 1000000000,
                'attributes': {
                    'logfire.span_type': 'log',
                    'logfire.level_name': 'warn',
                    'logfire.level_num': 13,
                    'logfire.msg_template': 'Validation on {schema_name} failed',
                    'logfire.msg': 'Validation on MyDataclass failed',
                    'code.filepath': 'test_pydantic_plugin.py',
                    'code.function': 'test_pydantic_plugin_with_dataclass',
                    'code.lineno': 123,
                    'schema_name': 'MyDataclass',
                    'error_count': 1,
                    'errors': '[{"type":"int_parsing","loc":["x"],"msg":"Input should be a valid integer, unable to parse string as an integer","input":"a"}]',
                    'logfire.json_schema': '{"type":"object","properties":{"schema_name":{},"error_count":{},"errors":{"type":"array","items":{"type":"object","properties":{"loc":{"type":"array","x-python-datatype":"tuple"}}}}}}',
                },
            }
        ]
    )


def test_pydantic_plugin_sample_rate_config(exporter: TestExporter) -> None:
    logfire.configure(
        send_to_logfire=False,
        trace_sample_rate=0.1,
        processors=[SimpleSpanProcessor(exporter)],
        id_generator=SeededRandomIdGenerator(),
        metric_readers=[InMemoryMetricReader()],
    )

    class MyModel(BaseModel, plugin_settings={'logfire': {'record': 'all'}}):
        x: int

    for _ in range(10):
        with pytest.raises(ValidationError):
            MyModel.model_validate({'x': 'a'})

    assert len(exporter.exported_spans_as_dict()) == 1


@pytest.mark.xfail(reason='We need to fix the nesting `trace_sample_rate` logic.')
def test_pydantic_plugin_plugin_settings_sample_rate(exporter: TestExporter) -> None:
    logfire.configure(
        send_to_logfire=False,
        processors=[SimpleSpanProcessor(exporter)],
        id_generator=SeededRandomIdGenerator(),
        metric_readers=[InMemoryMetricReader()],
    )

    class MyModel(BaseModel, plugin_settings={'logfire': {'record': 'all', 'trace_sample_rate': 0.4}}):
        x: int

    for _ in range(10):
        with pytest.raises(ValidationError):
            MyModel.model_validate({'x': 'a'})

    assert len(exporter.exported_spans_as_dict()) == 6


@pytest.mark.parametrize('tags', [['tag1', 'tag2'], ('tag1', 'tag2')])
def test_pydantic_plugin_plugin_settings_tags(exporter: TestExporter, tags: Any) -> None:
    class MyModel(BaseModel, plugin_settings={'logfire': {'record': 'failure', 'tags': tags}}):
        x: int

    with pytest.raises(ValidationError):
        MyModel.model_validate({'x': 'test'})

    span = exporter.exported_spans_as_dict()[0]
    assert span['attributes']['logfire.tags'] == ('tag1', 'tag2')


@pytest.mark.xfail(reason='We need to fix the nesting `trace_sample_rate` logic.')
def test_pydantic_plugin_plugin_settings_sample_rate_with_tag(exporter: TestExporter) -> None:
    logfire.configure(
        send_to_logfire=False,
        processors=[SimpleSpanProcessor(exporter)],
        id_generator=SeededRandomIdGenerator(),
        metric_readers=[InMemoryMetricReader()],
    )

    class MyModel(
        BaseModel, plugin_settings={'logfire': {'record': 'all', 'trace_sample_rate': 0.4, 'tags': 'test_tag'}}
    ):
        x: int

    for _ in range(10):
        with pytest.raises(ValidationError):
            MyModel.model_validate({'x': 'a'})

    assert len(exporter.exported_spans_as_dict()) == 6

    span = exporter.exported_spans_as_dict()[0]
    assert span['attributes']['logfire.tags'] == ('test_tag',)


def test_pydantic_plugin_nested_model(exporter: TestExporter):
    class Model1(BaseModel, plugin_settings={'logfire': {'record': 'all'}}):
        x: int

    class Model2(BaseModel, plugin_settings={'logfire': {'record': 'all'}}):
        m: Model1

        @field_validator('m', mode='before')
        def validate_m(cls, v: Any):
            return Model1.model_validate(v)

    Model2.model_validate({'m': {'x': 10}})
    with pytest.raises(ValidationError):
        Model2.model_validate({'m': {'x': 'y'}})

    assert exporter.exported_spans_as_dict() == snapshot(
        [
            {
                'name': 'pydantic.validate_python',
                'context': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 2000000000,
                'end_time': 3000000000,
                'attributes': {
                    'logfire.span_type': 'span',
                    'logfire.msg_template': 'Pydantic {schema_name} {validation_method}',
                    'logfire.msg': 'Pydantic Model1 validate_python succeeded',
                    'code.filepath': 'pydantic_plugin.py',
                    'code.function': '_on_enter',
                    'code.lineno': 123,
                    'result': '{"x":10}',
                    'logfire.json_schema': '{"type":"object","properties":{"schema_name":{},"validation_method":{},"input_data":{"type":"object"},"success":{},"result":{"type":"object","title":"Model1","x-python-datatype":"PydanticModel"}}}',
                    'success': True,
                    'input_data': '{"x":10}',
                    'schema_name': 'Model1',
                    'validation_method': 'validate_python',
                    'logfire.level_num': 9,
                    'logfire.level_name': 'info',
                },
            },
            {
                'name': 'pydantic.validate_python',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 4000000000,
                'attributes': {
                    'code.filepath': 'pydantic_plugin.py',
                    'code.function': '_on_enter',
                    'code.lineno': 123,
                    'logfire.msg_template': 'Pydantic {schema_name} {validation_method}',
                    'logfire.msg': 'Pydantic Model2 validate_python succeeded',
                    'logfire.json_schema': '{"type":"object","properties":{"schema_name":{},"validation_method":{},"input_data":{"type":"object"},"success":{},"result":{"type":"object","title":"Model2","x-python-datatype":"PydanticModel","properties":{"m":{"type":"object","title":"Model1","x-python-datatype":"PydanticModel"}}}}}',
                    'logfire.span_type': 'span',
                    'schema_name': 'Model2',
                    'validation_method': 'validate_python',
                    'input_data': '{"m":{"x":10}}',
                    'result': '{"m":{"x":10}}',
                    'success': True,
                    'logfire.level_num': 9,
                    'logfire.level_name': 'info',
                },
            },
            {
                'name': 'pydantic.validate_python',
                'context': {'trace_id': 2, 'span_id': 7, 'is_remote': False},
                'parent': {'trace_id': 2, 'span_id': 5, 'is_remote': False},
                'start_time': 6000000000,
                'end_time': 7000000000,
                'attributes': {
                    'logfire.span_type': 'span',
                    'logfire.msg_template': 'Pydantic {schema_name} {validation_method}',
                    'logfire.msg': 'Pydantic Model1 validate_python failed',
                    'code.filepath': 'pydantic_plugin.py',
                    'code.function': '_on_enter',
                    'code.lineno': 123,
                    'logfire.json_schema': '{"type":"object","properties":{"schema_name":{},"validation_method":{},"input_data":{"type":"object"},"success":{},"error_count":{},"errors":{"type":"array","items":{"type":"object","properties":{"loc":{"type":"array","x-python-datatype":"tuple"}}}}}}',
                    'success': False,
                    'input_data': '{"x":"y"}',
                    'schema_name': 'Model1',
                    'validation_method': 'validate_python',
                    'error_count': 1,
                    'errors': '[{"type":"int_parsing","loc":["x"],"msg":"Input should be a valid integer, unable to parse string as an integer","input":"y"}]',
                    'logfire.level_num': 13,
                    'logfire.level_name': 'warn',
                },
            },
            {
                'name': 'pydantic.validate_python',
                'context': {'trace_id': 2, 'span_id': 5, 'is_remote': False},
                'parent': None,
                'start_time': 5000000000,
                'end_time': 8000000000,
                'attributes': {
                    'code.filepath': 'pydantic_plugin.py',
                    'code.function': '_on_enter',
                    'code.lineno': 123,
                    'schema_name': 'Model2',
                    'logfire.msg_template': 'Pydantic {schema_name} {validation_method}',
                    'logfire.msg': 'Pydantic Model2 validate_python failed',
                    'logfire.json_schema': '{"type":"object","properties":{"schema_name":{},"validation_method":{},"input_data":{"type":"object"},"success":{},"error_count":{},"errors":{"type":"array","items":{"type":"object","properties":{"loc":{"type":"array","x-python-datatype":"tuple"}}}}}}',
                    'logfire.span_type': 'span',
                    'input_data': '{"m":{"x":"y"}}',
                    'validation_method': 'validate_python',
                    'success': False,
                    'error_count': 1,
                    'errors': '[{"type":"int_parsing","loc":["m","x"],"msg":"Input should be a valid integer, unable to parse string as an integer","input":"y"}]',
                    'logfire.level_num': 13,
                    'logfire.level_name': 'warn',
                },
            },
        ]
    )


def test_pydantic_plugin_python_exception(exporter: TestExporter) -> None:
    class MyModel(BaseModel, plugin_settings={'logfire': {'record': 'all'}}):
        x: int

        @field_validator('x')
        def validate_x(cls, v: Any) -> Any:
            raise TypeError('My error')

    with pytest.raises(TypeError):
        MyModel(x=1)

    assert exporter.exported_spans_as_dict() == snapshot(
        [
            {
                'name': 'pydantic.validate_python',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 3000000000,
                'attributes': {
                    'logfire.span_type': 'span',
                    'logfire.level_name': 'error',
                    'logfire.level_num': 17,
                    'logfire.msg_template': 'Pydantic {schema_name} {validation_method}',
                    'logfire.msg': 'Pydantic MyModel validate_python raised TypeError',
                    'code.filepath': 'pydantic_plugin.py',
                    'code.function': '_on_enter',
                    'code.lineno': 123,
                    'schema_name': 'MyModel',
                    'logfire.json_schema': '{"type":"object","properties":{"schema_name":{},"validation_method":{},"input_data":{"type":"object"},"success":{}}}',
                    'validation_method': 'validate_python',
                    'input_data': '{"x":1}',
                    'success': False,
                },
                'events': [
                    {
                        'name': 'exception',
                        'timestamp': 2000000000,
                        'attributes': {
                            'exception.type': 'TypeError',
                            'exception.message': 'My error',
                            'exception.stacktrace': 'TypeError: My error',
                            'exception.escaped': 'True',
                        },
                    }
                ],
            }
        ]
    )


def test_pydantic_plugin_python_exception_record_failure(exporter: TestExporter) -> None:
    class MyModel(BaseModel, plugin_settings={'logfire': {'record': 'failure'}}):
        x: int

        @field_validator('x')
        def validate_x(cls, v: Any) -> Any:
            raise TypeError('My error')

    with pytest.raises(TypeError):
        MyModel(x=1)

    assert exporter.exported_spans_as_dict() == snapshot(
        [
            {
                'name': 'Validation on {schema_name} raised {exception_type}',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 1000000000,
                'attributes': {
                    'logfire.span_type': 'log',
                    'logfire.level_name': 'error',
                    'logfire.level_num': 17,
                    'logfire.msg_template': 'Validation on {schema_name} raised {exception_type}',
                    'logfire.msg': 'Validation on MyModel raised TypeError',
                    'code.filepath': 'test_pydantic_plugin.py',
                    'code.function': 'test_pydantic_plugin_python_exception_record_failure',
                    'code.lineno': 123,
                    'schema_name': 'MyModel',
                    'logfire.json_schema': '{"type":"object","properties":{"schema_name":{},"exception_type":{}}}',
                    'exception_type': 'TypeError',
                },
                'events': [
                    {
                        'name': 'exception',
                        'timestamp': 2000000000,
                        'attributes': {
                            'exception.type': 'TypeError',
                            'exception.message': 'My error',
                            'exception.stacktrace': 'TypeError: My error',
                            'exception.escaped': 'False',
                        },
                    }
                ],
            }
        ]
    )
