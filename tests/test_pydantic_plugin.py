from __future__ import annotations

import importlib.metadata
import json
from typing import Any, cast

import pytest
from dirty_equals import IsInt
from opentelemetry.sdk.metrics.export import InMemoryMetricReader, MetricsData
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from pydantic import BaseModel, ConfigDict, ValidationError
from pydantic.dataclasses import dataclass as pydantic_dataclass
from pydantic.plugin import SchemaTypePath
from pydantic_core import core_schema

import logfire
from logfire._config import GLOBAL_CONFIG, PydanticPlugin
from logfire.integrations.pydantic_plugin import LogfirePydanticPlugin
from logfire.testing import SeededRandomIdGenerator, TestExporter


def _get_collected_metrics(metrics_reader: InMemoryMetricReader) -> list[dict[str, Any]]:
    collected_metrics = []
    exported_metrics = json.loads(cast(MetricsData, metrics_reader.get_metrics_data()).to_json())  # type: ignore

    for resource_metric in exported_metrics['resource_metrics']:
        for scope_metric in resource_metric['scope_metrics']:
            for metric in scope_metric['metrics']:
                if metric['name'].endswith('-successful-validation') or metric['name'].endswith('-failed-validation'):
                    collected_metrics.append(metric)
    return collected_metrics


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

    # insert_assert(exporter.exported_spans_as_dict(_include_pending_spans=True))
    assert exporter.exported_spans_as_dict(_include_pending_spans=True) == []


def test_pydantic_plugin_settings_record_override_pydantic_plugin_record(exporter: TestExporter) -> None:
    GLOBAL_CONFIG.pydantic_plugin.record = 'all'

    class MyModel(BaseModel, plugin_settings={'logfire': {'record': 'off'}}):
        x: int

    MyModel(x=1)

    # insert_assert(exporter.exported_spans_as_dict(_include_pending_spans=True))
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

    # insert_assert(exporter.exported_spans_as_dict(_include_pending_spans=True))
    assert exporter.exported_spans_as_dict(_include_pending_spans=True) == [
        {
            'name': 'Validation on MyModel failed',
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
                'logfire.json_schema': '{"type":"object","properties":{"schema_name":{},"error_count":{},"errors":{"type":"array","x-python-datatype":"list","items":{"type":"object","properties":{"loc":{"type":"array","x-python-datatype":"tuple"}}}}}}',
            },
        }
    ]

    metrics_collected = _get_collected_metrics(metrics_reader)
    # insert_assert(metrics_collected)
    assert metrics_collected == [
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
                'aggregation_temporality': 2,
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
                'aggregation_temporality': 2,
                'is_monotonic': True,
            },
        },
    ]


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

    metrics_collected = _get_collected_metrics(metrics_reader)
    # insert_assert(metrics_collected)
    assert metrics_collected == [
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
                'aggregation_temporality': 2,
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
                'aggregation_temporality': 2,
                'is_monotonic': True,
            },
        },
    ]


def test_pydantic_plugin_python_success(exporter: TestExporter, metrics_reader: InMemoryMetricReader) -> None:
    class MyModel(BaseModel, plugin_settings={'logfire': {'record': 'all'}}):
        x: int

    MyModel(x=1)

    # insert_assert(exporter.exported_spans_as_dict())
    assert exporter.exported_spans_as_dict() == [
        {
            'name': 'Validation successful result=MyModel(x=1)',
            'context': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
            'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
            'start_time': 2000000000,
            'end_time': 2000000000,
            'attributes': {
                'logfire.span_type': 'log',
                'logfire.level_name': 'debug',
                'logfire.level_num': 5,
                'logfire.msg_template': 'Validation successful {result=!r}',
                'logfire.msg': 'Validation successful result=MyModel(x=1)',
                'code.filepath': 'test_pydantic_plugin.py',
                'code.function': 'test_pydantic_plugin_python_success',
                'code.lineno': 123,
                'result': '{"x":1}',
                'logfire.json_schema': '{"type":"object","properties":{"result":{"type":"object","title":"MyModel","x-python-datatype":"PydanticModel"}}}',
            },
        },
        {
            'name': 'pydantic.validate_python',
            'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
            'parent': None,
            'start_time': 1000000000,
            'end_time': 3000000000,
            'attributes': {
                'code.filepath': 'pydantic_plugin.py',
                'code.function': '_on_enter',
                'code.lineno': 123,
                'schema_name': 'MyModel',
                'validation_method': 'validate_python',
                'input_data': '{"x":1}',
                'logfire.msg_template': 'Pydantic {schema_name} {validation_method}',
                'logfire.json_schema': '{"type":"object","properties":{"schema_name":{},"validation_method":{},"input_data":{"type":"object"}}}',
                'logfire.span_type': 'span',
                'logfire.msg': 'Pydantic MyModel validate_python',
            },
        },
    ]

    metrics_collected = _get_collected_metrics(metrics_reader)
    # insert_assert(metrics_collected)
    assert metrics_collected == [
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
                'aggregation_temporality': 2,
                'is_monotonic': True,
            },
        }
    ]


def test_pydantic_plugin_python_error_record_failure(
    exporter: TestExporter, metrics_reader: InMemoryMetricReader
) -> None:
    class MyModel(BaseModel, plugin_settings={'logfire': {'record': 'failure'}}):
        x: int

    with pytest.raises(ValidationError):
        MyModel(x='a')  # type: ignore

    with pytest.raises(ValidationError):
        MyModel(x='a')  # type: ignore

    # insert_assert(exporter.exported_spans_as_dict(_include_pending_spans=True))
    assert exporter.exported_spans_as_dict(_include_pending_spans=True) == [
        {
            'name': 'Validation on MyModel failed',
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
                'logfire.json_schema': '{"type":"object","properties":{"schema_name":{},"error_count":{},"errors":{"type":"array","x-python-datatype":"list","items":{"type":"object","properties":{"loc":{"type":"array","x-python-datatype":"tuple"}}}}}}',
            },
        },
        {
            'name': 'Validation on MyModel failed',
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
                'logfire.json_schema': '{"type":"object","properties":{"schema_name":{},"error_count":{},"errors":{"type":"array","x-python-datatype":"list","items":{"type":"object","properties":{"loc":{"type":"array","x-python-datatype":"tuple"}}}}}}',
            },
        },
    ]

    metrics_collected = _get_collected_metrics(metrics_reader)
    # insert_assert(metrics_collected)
    assert metrics_collected == [
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
                'aggregation_temporality': 2,
                'is_monotonic': True,
            },
        }
    ]


def test_pydantic_plugin_python_error(exporter: TestExporter) -> None:
    class MyModel(BaseModel, plugin_settings={'logfire': {'record': 'all'}}):
        x: int

    with pytest.raises(ValidationError):
        MyModel(x='a')  # type: ignore

    # insert_assert(exporter.exported_spans_as_dict())
    assert exporter.exported_spans_as_dict() == [
        {
            'name': 'Validation on MyModel failed',
            'context': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
            'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
            'start_time': 2000000000,
            'end_time': 2000000000,
            'attributes': {
                'logfire.span_type': 'log',
                'logfire.level_name': 'warn',
                'logfire.level_num': 13,
                'logfire.msg_template': 'Validation on {schema_name} failed',
                'logfire.msg': 'Validation on MyModel failed',
                'code.filepath': 'test_pydantic_plugin.py',
                'code.function': 'test_pydantic_plugin_python_error',
                'code.lineno': 123,
                'schema_name': 'MyModel',
                'error_count': 1,
                'errors': '[{"type":"int_parsing","loc":["x"],"msg":"Input should be a valid integer, unable to parse string as an integer","input":"a"}]',
                'logfire.json_schema': '{"type":"object","properties":{"schema_name":{},"error_count":{},"errors":{"type":"array","x-python-datatype":"list","items":{"type":"object","properties":{"loc":{"type":"array","x-python-datatype":"tuple"}}}}}}',
            },
        },
        {
            'name': 'pydantic.validate_python',
            'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
            'parent': None,
            'start_time': 1000000000,
            'end_time': 3000000000,
            'attributes': {
                'code.filepath': 'pydantic_plugin.py',
                'code.function': '_on_enter',
                'code.lineno': 123,
                'schema_name': 'MyModel',
                'validation_method': 'validate_python',
                'input_data': '{"x":"a"}',
                'logfire.msg_template': 'Pydantic {schema_name} {validation_method}',
                'logfire.json_schema': '{"type":"object","properties":{"schema_name":{},"validation_method":{},"input_data":{"type":"object"}}}',
                'logfire.span_type': 'span',
                'logfire.msg': 'Pydantic MyModel validate_python',
            },
        },
    ]


def test_pydantic_plugin_json_success(exporter: TestExporter) -> None:
    class MyModel(BaseModel, plugin_settings={'logfire': {'record': 'all'}}):
        x: int

    MyModel.model_validate_json('{"x":1}')

    # insert_assert(exporter.exported_spans_as_dict())
    assert exporter.exported_spans_as_dict() == [
        {
            'name': 'Validation successful result=MyModel(x=1)',
            'context': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
            'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
            'start_time': 2000000000,
            'end_time': 2000000000,
            'attributes': {
                'logfire.span_type': 'log',
                'logfire.level_name': 'debug',
                'logfire.level_num': 5,
                'logfire.msg_template': 'Validation successful {result=!r}',
                'logfire.msg': 'Validation successful result=MyModel(x=1)',
                'code.filepath': 'test_pydantic_plugin.py',
                'code.function': 'test_pydantic_plugin_json_success',
                'code.lineno': 123,
                'result': '{"x":1}',
                'logfire.json_schema': '{"type":"object","properties":{"result":{"type":"object","title":"MyModel","x-python-datatype":"PydanticModel"}}}',
            },
        },
        {
            'name': 'pydantic.validate_json',
            'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
            'parent': None,
            'start_time': 1000000000,
            'end_time': 3000000000,
            'attributes': {
                'code.filepath': 'pydantic_plugin.py',
                'code.function': '_on_enter',
                'code.lineno': 123,
                'schema_name': 'MyModel',
                'validation_method': 'validate_json',
                'input_data': '{"x":1}',
                'logfire.msg_template': 'Pydantic {schema_name} {validation_method}',
                'logfire.json_schema': '{"type":"object","properties":{"schema_name":{},"validation_method":{},"input_data":{}}}',
                'logfire.span_type': 'span',
                'logfire.msg': 'Pydantic MyModel validate_json',
            },
        },
    ]


def test_pydantic_plugin_json_error(exporter: TestExporter) -> None:
    class MyModel(BaseModel, plugin_settings={'logfire': {'record': 'all'}}):
        x: int

    with pytest.raises(ValidationError):
        MyModel.model_validate({'x': 'a'})

    # insert_assert(exporter.exported_spans_as_dict())
    assert exporter.exported_spans_as_dict() == [
        {
            'name': 'Validation on MyModel failed',
            'context': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
            'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
            'start_time': 2000000000,
            'end_time': 2000000000,
            'attributes': {
                'logfire.span_type': 'log',
                'logfire.level_name': 'warn',
                'logfire.level_num': 13,
                'logfire.msg_template': 'Validation on {schema_name} failed',
                'logfire.msg': 'Validation on MyModel failed',
                'code.filepath': 'test_pydantic_plugin.py',
                'code.function': 'test_pydantic_plugin_json_error',
                'code.lineno': 123,
                'schema_name': 'MyModel',
                'error_count': 1,
                'errors': '[{"type":"int_parsing","loc":["x"],"msg":"Input should be a valid integer, unable to parse string as an integer","input":"a"}]',
                'logfire.json_schema': '{"type":"object","properties":{"schema_name":{},"error_count":{},"errors":{"type":"array","x-python-datatype":"list","items":{"type":"object","properties":{"loc":{"type":"array","x-python-datatype":"tuple"}}}}}}',
            },
        },
        {
            'name': 'pydantic.validate_python',
            'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
            'parent': None,
            'start_time': 1000000000,
            'end_time': 3000000000,
            'attributes': {
                'code.filepath': 'pydantic_plugin.py',
                'code.function': '_on_enter',
                'code.lineno': 123,
                'schema_name': 'MyModel',
                'validation_method': 'validate_python',
                'input_data': '{"x":"a"}',
                'logfire.msg_template': 'Pydantic {schema_name} {validation_method}',
                'logfire.json_schema': '{"type":"object","properties":{"schema_name":{},"validation_method":{},"input_data":{"type":"object"}}}',
                'logfire.span_type': 'span',
                'logfire.msg': 'Pydantic MyModel validate_python',
            },
        },
    ]


def test_pydantic_plugin_strings_success(exporter: TestExporter) -> None:
    class MyModel(BaseModel, plugin_settings={'logfire': {'record': 'all'}}):
        x: int

    MyModel.model_validate_strings({'x': '1'}, strict=True)

    # insert_assert(exporter.exported_spans_as_dict())
    assert exporter.exported_spans_as_dict() == [
        {
            'name': 'Validation successful result=MyModel(x=1)',
            'context': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
            'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
            'start_time': 2000000000,
            'end_time': 2000000000,
            'attributes': {
                'logfire.span_type': 'log',
                'logfire.level_name': 'debug',
                'logfire.level_num': 5,
                'logfire.msg_template': 'Validation successful {result=!r}',
                'logfire.msg': 'Validation successful result=MyModel(x=1)',
                'code.filepath': 'test_pydantic_plugin.py',
                'code.function': 'test_pydantic_plugin_strings_success',
                'code.lineno': 123,
                'result': '{"x":1}',
                'logfire.json_schema': '{"type":"object","properties":{"result":{"type":"object","title":"MyModel","x-python-datatype":"PydanticModel"}}}',
            },
        },
        {
            'name': 'pydantic.validate_strings',
            'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
            'parent': None,
            'start_time': 1000000000,
            'end_time': 3000000000,
            'attributes': {
                'code.filepath': 'pydantic_plugin.py',
                'code.function': '_on_enter',
                'code.lineno': 123,
                'schema_name': 'MyModel',
                'validation_method': 'validate_strings',
                'input_data': '{"x":"1"}',
                'logfire.msg_template': 'Pydantic {schema_name} {validation_method}',
                'logfire.json_schema': '{"type":"object","properties":{"schema_name":{},"validation_method":{},"input_data":{"type":"object"}}}',
                'logfire.span_type': 'span',
                'logfire.msg': 'Pydantic MyModel validate_strings',
            },
        },
    ]


def test_pydantic_plugin_strings_error(exporter: TestExporter) -> None:
    class MyModel(BaseModel, plugin_settings={'logfire': {'record': 'all'}}):
        x: int

    with pytest.raises(ValidationError):
        MyModel.model_validate_strings({'x': 'a'})

    # insert_assert(exporter.exported_spans_as_dict())
    assert exporter.exported_spans_as_dict() == [
        {
            'name': 'Validation on MyModel failed',
            'context': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
            'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
            'start_time': 2000000000,
            'end_time': 2000000000,
            'attributes': {
                'logfire.span_type': 'log',
                'logfire.level_name': 'warn',
                'logfire.level_num': 13,
                'logfire.msg_template': 'Validation on {schema_name} failed',
                'logfire.msg': 'Validation on MyModel failed',
                'code.filepath': 'test_pydantic_plugin.py',
                'code.function': 'test_pydantic_plugin_strings_error',
                'code.lineno': 123,
                'schema_name': 'MyModel',
                'error_count': 1,
                'errors': '[{"type":"int_parsing","loc":["x"],"msg":"Input should be a valid integer, unable to parse string as an integer","input":"a"}]',
                'logfire.json_schema': '{"type":"object","properties":{"schema_name":{},"error_count":{},"errors":{"type":"array","x-python-datatype":"list","items":{"type":"object","properties":{"loc":{"type":"array","x-python-datatype":"tuple"}}}}}}',
            },
        },
        {
            'name': 'pydantic.validate_strings',
            'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
            'parent': None,
            'start_time': 1000000000,
            'end_time': 3000000000,
            'attributes': {
                'code.filepath': 'pydantic_plugin.py',
                'code.function': '_on_enter',
                'code.lineno': 123,
                'schema_name': 'MyModel',
                'validation_method': 'validate_strings',
                'input_data': '{"x":"a"}',
                'logfire.msg_template': 'Pydantic {schema_name} {validation_method}',
                'logfire.json_schema': '{"type":"object","properties":{"schema_name":{},"validation_method":{},"input_data":{"type":"object"}}}',
                'logfire.span_type': 'span',
                'logfire.msg': 'Pydantic MyModel validate_strings',
            },
        },
    ]


def test_pydantic_plugin_with_dataclass(exporter: TestExporter) -> None:
    @pydantic_dataclass(config=ConfigDict(plugin_settings={'logfire': {'record': 'failure'}}))
    class MyDataclass:
        x: int

    with pytest.raises(ValidationError):
        MyDataclass(x='a')

    # insert_assert(exporter.exported_spans_as_dict())
    assert exporter.exported_spans_as_dict() == [
        {
            'name': 'Validation on MyDataclass failed',
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
                'logfire.json_schema': '{"type":"object","properties":{"schema_name":{},"error_count":{},"errors":{"type":"array","x-python-datatype":"list","items":{"type":"object","properties":{"loc":{"type":"array","x-python-datatype":"tuple"}}}}}}',
            },
        }
    ]


def test_pydantic_plugin_sample_rate_config() -> None:
    exporter = TestExporter()

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

    assert len(exporter.exported_spans_as_dict()) == 2


@pytest.mark.xfail(reason='We need to fix the nesting `trace_sample_rate` logic.')
def test_pydantic_plugin_plugin_settings_sample_rate(exporter: TestExporter) -> None:
    exporter = TestExporter()

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
    exporter = TestExporter()

    logfire.configure(
        send_to_logfire=False,
        processors=[SimpleSpanProcessor(exporter)],
        id_generator=SeededRandomIdGenerator(),
        metric_readers=[InMemoryMetricReader()],
    )

    class MyModel(BaseModel, plugin_settings={'logfire': {'record': 'failure', 'tags': tags}}):
        x: int

    with pytest.raises(ValidationError):
        MyModel.model_validate({'x': 'test'})

    span = exporter.exported_spans_as_dict()[0]
    assert span['attributes']['logfire.tags'] == ('tag1', 'tag2')


@pytest.mark.xfail(reason='We need to fix the nesting `trace_sample_rate` logic.')
def test_pydantic_plugin_plugin_settings_sample_rate_with_tag(exporter: TestExporter) -> None:
    exporter = TestExporter()

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
