from __future__ import annotations

import importlib.metadata
import os
from typing import TYPE_CHECKING, Any
from unittest.mock import patch

import cloudpickle
import pytest
import sqlmodel
from dirty_equals import IsInt
from inline_snapshot import snapshot
from opentelemetry.sdk.metrics.export import AggregationTemporality, InMemoryMetricReader
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    TypeAdapter,
    ValidationError,
    __version__ as pydantic_version,
    field_validator,
)
from pydantic.dataclasses import dataclass as pydantic_dataclass
from pydantic_core import core_schema
from typing_extensions import Annotated

import logfire
from logfire._internal.config import GLOBAL_CONFIG
from logfire._internal.utils import get_version
from logfire.integrations.pydantic import (
    LogfirePydanticPlugin,
    get_schema_name,
)
from logfire.testing import SeededRandomIdGenerator, TestExporter
from tests.test_metrics import get_collected_metrics

pytestmark = pytest.mark.skipif(
    get_version(pydantic_version) < get_version('2.5.0'),
    reason='Skipping all tests for versions less than 2.5.',
)

if TYPE_CHECKING:
    from pydantic.plugin import PydanticPluginProtocol, SchemaTypePath, ValidatePythonHandlerProtocol

try:
    from pydantic.plugin import PydanticPluginProtocol, SchemaTypePath, ValidatePythonHandlerProtocol
except ImportError:
    # it's fine, pydantic version <v2.5
    pass


def test_plugin_listed():
    found = True
    entry_points: list[str] = []
    for d in importlib.metadata.distributions():
        for ep in d.entry_points:
            if ep.group == 'pydantic' and ep.value == 'logfire':  # pragma: no cover
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
        metrics=logfire.MetricsOptions(additional_readers=[InMemoryMetricReader()]),
    )
    logfire.instrument_pydantic(record='off')
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
    logfire.instrument_pydantic()

    class MyModel(BaseModel, plugin_settings={'logfire': {'record': 'off'}}):
        x: int

    MyModel(x=1)

    assert exporter.exported_spans_as_dict(_include_pending_spans=True) == []


@pytest.mark.parametrize(
    'include,exclude,module,name,expected_to_include',
    (  # type: ignore
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
        metrics=logfire.MetricsOptions(additional_readers=[InMemoryMetricReader()]),
    )
    logfire.instrument_pydantic(record='all', include=include, exclude=exclude)
    plugin = LogfirePydanticPlugin()

    result = plugin.new_schema_validator(
        core_schema.int_schema(), None, SchemaTypePath(module=module, name=name), 'BaseModel', None, {}
    )
    if expected_to_include:
        assert result != (None, None, None)
    else:
        assert result == (None, None, None)


def test_get_schema_name():
    # In particular this tests schemas with type 'definitions'

    class Model1(BaseModel):
        x: int | list[Model1]

    class Model2(BaseModel):
        x: Model1

    assert get_schema_name(Model1.__pydantic_core_schema__) == 'Model1'
    assert get_schema_name(Model2.__pydantic_core_schema__) == 'Model2'


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
                'name': 'pydantic.validations',
                'description': '',
                'unit': '',
                'data': {
                    'data_points': [
                        {
                            'attributes': {
                                'validation_method': 'validate_python',
                                'schema_name': 'MyModel',
                                'success': True,
                            },
                            'start_time_unix_nano': IsInt(gt=0),
                            'time_unix_nano': IsInt(gt=0),
                            'value': 1,
                            'exemplars': [],
                        },
                        {
                            'attributes': {
                                'success': False,
                                'schema_name': 'MyModel',
                                'validation_method': 'validate_python',
                            },
                            'start_time_unix_nano': IsInt(gt=0),
                            'time_unix_nano': IsInt(gt=0),
                            'value': 1,
                            'exemplars': [],
                        },
                    ],
                    'aggregation_temporality': AggregationTemporality.DELTA,
                    'is_monotonic': True,
                },
            }
        ]
    )


def test_pydantic_plugin_metrics(metrics_reader: InMemoryMetricReader) -> None:
    class MyModel(BaseModel, plugin_settings={'logfire': {'record': 'metrics'}}):
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
                'name': 'pydantic.validations',
                'description': '',
                'unit': '',
                'data': {
                    'data_points': [
                        {
                            'attributes': {
                                'validation_method': 'validate_python',
                                'schema_name': 'MyModel',
                                'success': True,
                            },
                            'start_time_unix_nano': IsInt(gt=0),
                            'time_unix_nano': IsInt(gt=0),
                            'value': 3,
                            'exemplars': [],
                        },
                        {
                            'attributes': {
                                'success': False,
                                'schema_name': 'MyModel',
                                'validation_method': 'validate_python',
                            },
                            'start_time_unix_nano': IsInt(gt=0),
                            'time_unix_nano': IsInt(gt=0),
                            'value': 2,
                            'exemplars': [],
                        },
                    ],
                    'aggregation_temporality': AggregationTemporality.DELTA,
                    'is_monotonic': True,
                },
            }
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
                    'code.filepath': 'test_pydantic_plugin.py',
                    'code.function': 'test_pydantic_plugin_python_success',
                    'code.lineno': 123,
                    'result': '{"x":1}',
                    'logfire.json_schema': '{"type":"object","properties":{"schema_name":{},"validation_method":{},"input_data":{"type":"object"},"success":{},"result":{"type":"object","title":"MyModel","x-python-datatype":"PydanticModel"}}}',
                    'success': True,
                    'input_data': '{"x":1}',
                    'schema_name': 'MyModel',
                    'validation_method': 'validate_python',
                    'logfire.level_num': 9,
                },
            }
        ]
    )

    metrics_collected = get_collected_metrics(metrics_reader)
    assert metrics_collected == snapshot(
        [
            {
                'name': 'pydantic.validations',
                'description': '',
                'unit': '',
                'data': {
                    'data_points': [
                        {
                            'attributes': {
                                'validation_method': 'validate_python',
                                'schema_name': 'MyModel',
                                'success': True,
                            },
                            'start_time_unix_nano': IsInt(gt=0),
                            'time_unix_nano': IsInt(gt=0),
                            'value': 1,
                            'exemplars': [
                                {
                                    'filtered_attributes': {},
                                    'value': 1,
                                    'time_unix_nano': IsInt(),
                                    'span_id': 1,
                                    'trace_id': 1,
                                }
                            ],
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
                'name': 'pydantic.validations',
                'description': '',
                'unit': '',
                'data': {
                    'data_points': [
                        {
                            'attributes': {
                                'validation_method': 'validate_python',
                                'schema_name': 'MyModel',
                                'success': False,
                            },
                            'start_time_unix_nano': IsInt(gt=0),
                            'time_unix_nano': IsInt(gt=0),
                            'value': 2,
                            'exemplars': [],
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
                    'code.filepath': 'test_pydantic_plugin.py',
                    'code.function': 'test_pydantic_plugin_python_error',
                    'code.lineno': 123,
                    'schema_name': 'MyModel',
                    'error_count': 1,
                    'errors': '[{"type":"int_parsing","loc":["x"],"msg":"Input should be a valid integer, unable to parse string as an integer","input":"a"}]',
                    'logfire.json_schema': '{"type":"object","properties":{"schema_name":{},"validation_method":{},"input_data":{"type":"object"},"success":{},"error_count":{},"errors":{"type":"array","items":{"type":"object","properties":{"loc":{"type":"array","x-python-datatype":"tuple"}}}}}}',
                    'success': False,
                    'validation_method': 'validate_python',
                    'input_data': '{"x":"a"}',
                    'logfire.level_num': 13,
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
                    'code.filepath': 'test_pydantic_plugin.py',
                    'code.function': 'test_pydantic_plugin_json_success',
                    'code.lineno': 123,
                    'result': '{"x":1}',
                    'logfire.json_schema': '{"type":"object","properties":{"schema_name":{},"validation_method":{},"input_data":{},"success":{},"result":{"type":"object","title":"MyModel","x-python-datatype":"PydanticModel"}}}',
                    'success': True,
                    'input_data': '{"x":1}',
                    'schema_name': 'MyModel',
                    'validation_method': 'validate_json',
                    'logfire.level_num': 9,
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
                    'code.filepath': 'test_pydantic_plugin.py',
                    'code.function': 'test_pydantic_plugin_json_error',
                    'code.lineno': 123,
                    'schema_name': 'MyModel',
                    'error_count': 1,
                    'errors': '[{"type":"int_parsing","loc":["x"],"msg":"Input should be a valid integer, unable to parse string as an integer","input":"a"}]',
                    'logfire.json_schema': '{"type":"object","properties":{"schema_name":{},"validation_method":{},"input_data":{"type":"object"},"success":{},"error_count":{},"errors":{"type":"array","items":{"type":"object","properties":{"loc":{"type":"array","x-python-datatype":"tuple"}}}}}}',
                    'success': False,
                    'validation_method': 'validate_python',
                    'input_data': '{"x":"a"}',
                    'logfire.level_num': 13,
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
                    'code.filepath': 'test_pydantic_plugin.py',
                    'code.function': 'test_pydantic_plugin_strings_success',
                    'code.lineno': 123,
                    'result': '{"x":1}',
                    'logfire.json_schema': '{"type":"object","properties":{"schema_name":{},"validation_method":{},"input_data":{"type":"object"},"success":{},"result":{"type":"object","title":"MyModel","x-python-datatype":"PydanticModel"}}}',
                    'success': True,
                    'input_data': '{"x":"1"}',
                    'schema_name': 'MyModel',
                    'validation_method': 'validate_strings',
                    'logfire.level_num': 9,
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
                    'code.filepath': 'test_pydantic_plugin.py',
                    'code.function': 'test_pydantic_plugin_strings_error',
                    'code.lineno': 123,
                    'schema_name': 'MyModel',
                    'error_count': 1,
                    'errors': '[{"type":"int_parsing","loc":["x"],"msg":"Input should be a valid integer, unable to parse string as an integer","input":"a"}]',
                    'logfire.json_schema': '{"type":"object","properties":{"schema_name":{},"validation_method":{},"input_data":{"type":"object"},"success":{},"error_count":{},"errors":{"type":"array","items":{"type":"object","properties":{"loc":{"type":"array","x-python-datatype":"tuple"}}}}}}',
                    'success': False,
                    'validation_method': 'validate_strings',
                    'input_data': '{"x":"a"}',
                    'logfire.level_num': 13,
                },
            }
        ]
    )


def test_pydantic_plugin_with_dataclass(exporter: TestExporter) -> None:
    @pydantic_dataclass(config=ConfigDict(plugin_settings={'logfire': {'record': 'failure'}}))
    class MyDataclass:
        x: int

    with pytest.raises(ValidationError):
        MyDataclass(x='a')  # type: ignore

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


def test_pydantic_plugin_sample_rate_config(exporter: TestExporter, config_kwargs: dict[str, Any]) -> None:
    config_kwargs.update(
        sampling=logfire.SamplingOptions(head=0.1),
        advanced=logfire.AdvancedOptions(id_generator=SeededRandomIdGenerator()),
    )
    logfire.configure(**config_kwargs)

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
        additional_span_processors=[SimpleSpanProcessor(exporter)],
        advanced=logfire.AdvancedOptions(
            id_generator=SeededRandomIdGenerator(),
        ),
        metrics=logfire.MetricsOptions(additional_readers=[InMemoryMetricReader()]),
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
        additional_span_processors=[SimpleSpanProcessor(exporter)],
        advanced=logfire.AdvancedOptions(
            id_generator=SeededRandomIdGenerator(),
        ),
        metrics=logfire.MetricsOptions(additional_readers=[InMemoryMetricReader()]),
    )

    class MyModel(
        BaseModel, plugin_settings={'logfire': {'record': 'all', 'trace_sample_rate': 0.4, 'tags': 'test_tag'}}
    ):
        x: int

    for _ in range(10):
        with pytest.raises(ValidationError):
            MyModel.model_validate({'x': 'a'})

    assert len(exporter.exported_spans_as_dict()) == 6

    # TODO(Marcelo): Why are those lines not being reached?
    span = exporter.exported_spans_as_dict()[0]  # pragma: no cover
    assert span['attributes']['logfire.tags'] == ('test_tag',)  # pragma: no cover


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
                    'code.filepath': 'test_pydantic_plugin.py',
                    'code.function': 'validate_m',
                    'code.lineno': 123,
                    'result': '{"x":10}',
                    'logfire.json_schema': '{"type":"object","properties":{"schema_name":{},"validation_method":{},"input_data":{"type":"object"},"success":{},"result":{"type":"object","title":"Model1","x-python-datatype":"PydanticModel"}}}',
                    'success': True,
                    'input_data': '{"x":10}',
                    'schema_name': 'Model1',
                    'validation_method': 'validate_python',
                    'logfire.level_num': 9,
                },
            },
            {
                'name': 'pydantic.validate_python',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 4000000000,
                'attributes': {
                    'code.filepath': 'test_pydantic_plugin.py',
                    'code.function': 'test_pydantic_plugin_nested_model',
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
                    'code.filepath': 'test_pydantic_plugin.py',
                    'code.function': 'validate_m',
                    'code.lineno': 123,
                    'logfire.json_schema': '{"type":"object","properties":{"schema_name":{},"validation_method":{},"input_data":{"type":"object"},"success":{},"error_count":{},"errors":{"type":"array","items":{"type":"object","properties":{"loc":{"type":"array","x-python-datatype":"tuple"}}}}}}',
                    'success': False,
                    'input_data': '{"x":"y"}',
                    'schema_name': 'Model1',
                    'validation_method': 'validate_python',
                    'error_count': 1,
                    'errors': '[{"type":"int_parsing","loc":["x"],"msg":"Input should be a valid integer, unable to parse string as an integer","input":"y"}]',
                    'logfire.level_num': 13,
                },
            },
            {
                'name': 'pydantic.validate_python',
                'context': {'trace_id': 2, 'span_id': 5, 'is_remote': False},
                'parent': None,
                'start_time': 5000000000,
                'end_time': 8000000000,
                'attributes': {
                    'code.filepath': 'test_pydantic_plugin.py',
                    'code.function': 'test_pydantic_plugin_nested_model',
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
                    'logfire.level_num': 17,
                    'logfire.msg_template': 'Pydantic {schema_name} {validation_method}',
                    'logfire.msg': 'Pydantic MyModel validate_python raised TypeError',
                    'code.filepath': 'test_pydantic_plugin.py',
                    'code.function': 'test_pydantic_plugin_python_exception',
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


def test_old_plugin_style(exporter: TestExporter) -> None:
    # Test that plugins for the old API still work together with the logfire plugin.

    events: list[str] = []

    class Handler(ValidatePythonHandlerProtocol):
        def on_success(self, result: Any) -> None:
            events.append('success')

        def on_error(self, error: ValidationError) -> None:
            events.append('error')

        def on_exception(self, exception: Exception) -> None:
            events.append('exception')

    class OldPlugin(PydanticPluginProtocol):
        def new_schema_validator(self, *_: Any, **__: Any) -> Any:
            return Handler(), None, None

    class DummyPlugin:
        def new_schema_validator(self, *_: Any, **__: Any) -> Any:
            # Test returning a class that has none of the expected methods
            # and is also not callable (i.e. also doesn't satisfy the new API).
            return DummyPlugin(), None, None

    from pydantic.plugin import _loader

    _loader.get_plugins()
    _loader._plugins['old'] = OldPlugin()  # type: ignore
    _loader._plugins['dummy'] = DummyPlugin()  # type: ignore

    try:

        class MyModel(BaseModel, plugin_settings={'logfire': {'record': 'all'}}):
            x: int

            @field_validator('x')
            def validate_x(cls, v: Any) -> Any:
                if v == 1:
                    return v
                raise TypeError('My error')

        MyModel(x=1)
        with pytest.raises(TypeError):
            MyModel(x=2)
        with pytest.raises(ValidationError):
            MyModel(x='a')  # type: ignore

        assert events == ['success', 'exception', 'error']

        assert exporter.exported_spans_as_dict() == snapshot(
            [
                {
                    'name': 'pydantic.validate_python',
                    'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                    'parent': None,
                    'start_time': 1000000000,
                    'end_time': 2000000000,
                    'attributes': {
                        'code.filepath': 'test_pydantic_plugin.py',
                        'code.function': 'test_old_plugin_style',
                        'code.lineno': 123,
                        'schema_name': 'MyModel',
                        'validation_method': 'validate_python',
                        'input_data': '{"x":1}',
                        'logfire.msg_template': 'Pydantic {schema_name} {validation_method}',
                        'logfire.level_num': 9,
                        'logfire.span_type': 'span',
                        'success': True,
                        'result': '{"x":1}',
                        'logfire.msg': 'Pydantic MyModel validate_python succeeded',
                        'logfire.json_schema': '{"type":"object","properties":{"schema_name":{},"validation_method":{},"input_data":{"type":"object"},"success":{},"result":{"type":"object","title":"MyModel","x-python-datatype":"PydanticModel"}}}',
                    },
                },
                {
                    'name': 'pydantic.validate_python',
                    'context': {'trace_id': 2, 'span_id': 3, 'is_remote': False},
                    'parent': None,
                    'start_time': 3000000000,
                    'end_time': 5000000000,
                    'attributes': {
                        'code.filepath': 'test_pydantic_plugin.py',
                        'code.function': 'test_old_plugin_style',
                        'code.lineno': 123,
                        'schema_name': 'MyModel',
                        'validation_method': 'validate_python',
                        'input_data': '{"x":2}',
                        'logfire.msg_template': 'Pydantic {schema_name} {validation_method}',
                        'logfire.span_type': 'span',
                        'success': False,
                        'logfire.msg': 'Pydantic MyModel validate_python raised TypeError',
                        'logfire.level_num': 17,
                        'logfire.json_schema': '{"type":"object","properties":{"schema_name":{},"validation_method":{},"input_data":{"type":"object"},"success":{}}}',
                    },
                    'events': [
                        {
                            'name': 'exception',
                            'timestamp': 4000000000,
                            'attributes': {
                                'exception.type': 'TypeError',
                                'exception.message': 'My error',
                                'exception.stacktrace': 'TypeError: My error',
                                'exception.escaped': 'True',
                            },
                        }
                    ],
                },
                {
                    'name': 'pydantic.validate_python',
                    'context': {'trace_id': 3, 'span_id': 5, 'is_remote': False},
                    'parent': None,
                    'start_time': 6000000000,
                    'end_time': 7000000000,
                    'attributes': {
                        'code.filepath': 'test_pydantic_plugin.py',
                        'code.function': 'test_old_plugin_style',
                        'code.lineno': 123,
                        'schema_name': 'MyModel',
                        'validation_method': 'validate_python',
                        'input_data': '{"x":"a"}',
                        'logfire.msg_template': 'Pydantic {schema_name} {validation_method}',
                        'logfire.span_type': 'span',
                        'success': False,
                        'error_count': 1,
                        'errors': '[{"type":"int_parsing","loc":["x"],"msg":"Input should be a valid integer, unable to parse string as an integer","input":"a"}]',
                        'logfire.msg': 'Pydantic MyModel validate_python failed',
                        'logfire.level_num': 13,
                        'logfire.json_schema': '{"type":"object","properties":{"schema_name":{},"validation_method":{},"input_data":{"type":"object"},"success":{},"error_count":{},"errors":{"type":"array","items":{"type":"object","properties":{"loc":{"type":"array","x-python-datatype":"tuple"}}}}}}',
                    },
                },
            ]
        )
    finally:
        del _loader._plugins['old']  # type: ignore
        del _loader._plugins['dummy']  # type: ignore


def test_function_validator(exporter: TestExporter):
    def double(v: Any) -> Any:
        return v * 2

    MyNumber = Annotated[int, AfterValidator(double)]

    config = ConfigDict(plugin_settings={'logfire': {'record': 'all'}})
    MyNumberAdapter = TypeAdapter(MyNumber, config=config)  # type: ignore

    assert MyNumberAdapter.validate_python(3) == 6

    assert exporter.exported_spans_as_dict() == snapshot(
        [
            {
                'name': 'pydantic.validate_python',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 2000000000,
                'attributes': {
                    'code.filepath': 'test_pydantic_plugin.py',
                    'code.function': 'test_function_validator',
                    'code.lineno': 123,
                    'schema_name': 'int',
                    'validation_method': 'validate_python',
                    'input_data': 3,
                    'logfire.msg_template': 'Pydantic {schema_name} {validation_method}',
                    'logfire.level_num': 9,
                    'logfire.span_type': 'span',
                    'success': True,
                    'result': 6,
                    'logfire.msg': 'Pydantic int validate_python succeeded',
                    'logfire.json_schema': '{"type":"object","properties":{"schema_name":{},"validation_method":{},"input_data":{},"success":{},"result":{}}}',
                },
            }
        ]
    )


def test_record_all_env_var(exporter: TestExporter) -> None:
    # Pretend that logfire.configure() hasn't been called yet.
    GLOBAL_CONFIG._initialized = False  # type: ignore

    with patch.dict(os.environ, {'LOGFIRE_PYDANTIC_PLUGIN_RECORD': 'all'}):
        # This model should be instrumented even though logfire.configure() hasn't been called
        # because of the LOGFIRE_PYDANTIC_PLUGIN_RECORD env var.
        class MyModel(BaseModel):
            x: int

        # But validations shouldn't be recorded yet.
        MyModel(x=1)
        assert exporter.exported_spans_as_dict() == []

        # Equivalent to calling logfire.configure() with the args in the `config` test fixture.
        GLOBAL_CONFIG._initialized = True  # type: ignore

        MyModel(x=2)
        assert exporter.exported_spans_as_dict() == snapshot(
            [
                {
                    'name': 'pydantic.validate_python',
                    'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                    'parent': None,
                    'start_time': 1000000000,
                    'end_time': 2000000000,
                    'attributes': {
                        'code.filepath': 'test_pydantic_plugin.py',
                        'code.function': 'test_record_all_env_var',
                        'code.lineno': 123,
                        'schema_name': 'MyModel',
                        'validation_method': 'validate_python',
                        'input_data': '{"x":2}',
                        'logfire.msg_template': 'Pydantic {schema_name} {validation_method}',
                        'logfire.level_num': 9,
                        'logfire.span_type': 'span',
                        'success': True,
                        'result': '{"x":2}',
                        'logfire.msg': 'Pydantic MyModel validate_python succeeded',
                        'logfire.json_schema': '{"type":"object","properties":{"schema_name":{},"validation_method":{},"input_data":{"type":"object"},"success":{},"result":{"type":"object","title":"MyModel","x-python-datatype":"PydanticModel"}}}',
                    },
                }
            ]
        )


def test_record_failure_env_var(exporter: TestExporter) -> None:
    # Same as test_record_all_env_var but with LOGFIRE_PYDANTIC_PLUGIN_RECORD=failure.

    GLOBAL_CONFIG._initialized = False  # type: ignore

    with patch.dict(os.environ, {'LOGFIRE_PYDANTIC_PLUGIN_RECORD': 'failure'}):

        class MyModel(BaseModel):
            x: int

        with pytest.raises(ValidationError):
            MyModel(x='a')  # type: ignore
        assert exporter.exported_spans_as_dict() == []

        GLOBAL_CONFIG._initialized = True  # type: ignore

        with pytest.raises(ValidationError):
            MyModel(x='b')  # type: ignore
        assert exporter.exported_spans_as_dict() == snapshot(
            [
                {
                    'name': 'Validation on {schema_name} failed',
                    'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                    'parent': None,
                    'start_time': 1000000000,
                    'end_time': 1000000000,
                    'attributes': {
                        'code.filepath': 'test_pydantic_plugin.py',
                        'code.function': 'test_record_failure_env_var',
                        'code.lineno': 123,
                        'schema_name': 'MyModel',
                        'logfire.msg_template': 'Validation on {schema_name} failed',
                        'logfire.level_num': 13,
                        'error_count': 1,
                        'errors': '[{"type":"int_parsing","loc":["x"],"msg":"Input should be a valid integer, unable to parse string as an integer","input":"b"}]',
                        'logfire.span_type': 'log',
                        'logfire.msg': 'Validation on MyModel failed',
                        'logfire.json_schema': '{"type":"object","properties":{"schema_name":{},"error_count":{},"errors":{"type":"array","items":{"type":"object","properties":{"loc":{"type":"array","x-python-datatype":"tuple"}}}}}}',
                    },
                }
            ]
        )


def test_record_metrics_env_var(metrics_reader: InMemoryMetricReader) -> None:
    # Same as test_record_all_env_var but with LOGFIRE_PYDANTIC_PLUGIN_RECORD=metrics.

    GLOBAL_CONFIG._initialized = False  # type: ignore

    with patch.dict(os.environ, {'LOGFIRE_PYDANTIC_PLUGIN_RECORD': 'metrics'}):

        class MyModel(BaseModel):
            x: int

        MyModel(x=1)
        assert metrics_reader.get_metrics_data() is None  # type: ignore

        GLOBAL_CONFIG._initialized = True  # type: ignore

        MyModel(x=2)
        assert get_collected_metrics(metrics_reader) == snapshot(
            [
                {
                    'name': 'pydantic.validations',
                    'description': '',
                    'unit': '',
                    'data': {
                        'data_points': [
                            {
                                'attributes': {
                                    'success': True,
                                    'schema_name': 'MyModel',
                                    'validation_method': 'validate_python',
                                },
                                'start_time_unix_nano': IsInt(gt=0),
                                'time_unix_nano': IsInt(gt=0),
                                'value': 1,
                                'exemplars': [],
                            }
                        ],
                        'aggregation_temporality': 1,
                        'is_monotonic': True,
                    },
                }
            ]
        )


def test_cloudpickle():
    class MyModel(BaseModel):
        x: int

    m = MyModel(x=1)
    assert cloudpickle.loads(cloudpickle.dumps(m)).model_dump() == m.model_dump() == {'x': 1}  # type: ignore


def test_sqlmodel_pydantic_plugin(exporter: TestExporter) -> None:
    logfire.instrument_pydantic()

    class Hero(sqlmodel.SQLModel, table=True):
        id: int = sqlmodel.Field(default=1, primary_key=True)

    Hero.model_validate({})

    assert exporter.exported_spans_as_dict() == snapshot(
        [
            {
                'name': 'pydantic.validate_python',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 2000000000,
                'attributes': {
                    'code.filepath': 'test_pydantic_plugin.py',
                    'code.function': 'test_sqlmodel_pydantic_plugin',
                    'code.lineno': 123,
                    'schema_name': 'Hero',
                    'validation_method': 'validate_python',
                    'input_data': '{}',
                    'logfire.msg_template': 'Pydantic {schema_name} {validation_method}',
                    'logfire.level_num': 9,
                    'logfire.span_type': 'span',
                    'success': True,
                    'result': '{"id":1}',
                    'logfire.msg': 'Pydantic Hero validate_python succeeded',
                    'logfire.json_schema': '{"type":"object","properties":{"schema_name":{},"validation_method":{},"input_data":{"type":"object"},"success":{},"result":{"type":"object","title":"Hero","x-python-datatype":"PydanticModel"}}}',
                },
            }
        ]
    )
