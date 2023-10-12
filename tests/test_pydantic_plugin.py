import importlib.metadata

import pytest
from dirty_equals import IsJson
from pydantic import BaseModel, ValidationError

from logfire import Logfire

from .conftest import TestExporter


@pytest.fixture(scope='module', autouse=True)
def clear_pydantic_plugins_cache():
    """Clear any existing Pydantic plugins."""
    from pydantic.plugin import _loader

    assert _loader._loading_plugins is False
    _loader._plugins = None


def test_plugin_listed():
    found = True
    entry_points = []
    for d in importlib.metadata.distributions():
        for ep in d.entry_points:
            if ep.group == 'pydantic' and ep.value == 'logfire':
                found = True
            entry_points.append(f'group={ep.group} value={ep.value}')
    assert found, 'logfire pydantic plugin not found, entrypoints:' + '\n'.join(entry_points)


def test_check_plugin_installed(logfire: Logfire, mocker):
    """Check Pydantic has found the logfire pydantic plugin."""
    mocker.patch('logfire.integrations.pydantic_plugin.logfire', new=logfire)

    from pydantic.plugin import _loader

    print(_loader.__file__)
    assert repr(next(iter(_loader.get_plugins()))) == 'LogfirePydanticPlugin(enabled=True)'


def test_pydantic_plugin_python_success(logfire: Logfire, exporter: TestExporter, mocker) -> None:
    mocker.patch('logfire.integrations.pydantic_plugin.logfire', new=logfire)

    class MyModel(BaseModel):
        x: int

    MyModel(x=1)

    # insert_assert(exporter.exported_spans_as_dict(full_attributes=True))
    assert exporter.exported_spans_as_dict(full_attributes=True) == [
        {
            'name': 'Pydantic MyModel validate_python',
            'context': {'trace_id': 1, 'span_id': 2, 'is_remote': False},
            'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
            'start_time': 1,
            'end_time': 1,
            'attributes': {
                'logfire.log_type': 'start_span',
                'logfire.msg_template': 'Pydantic {schema_name} {validation_method}',
                'schema_name': 'MyModel',
                'validation_method': 'validate_python',
                'input_data__JSON': '{"x":1}',
                'span_name': 'pydantic.validate_python',
            },
        },
        {
            'name': 'Validation successful result=MyModel(x=1)',
            'context': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
            'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
            'start_time': 2,
            'end_time': 2,
            'attributes': {
                'result__JSON': '{"$__datatype__":"BaseModel","data":{"x":1},"cls":"MyModel"}',
                'logfire.log_type': 'log',
                'logfire.level': 'debug',
                'logfire.msg_template': 'Validation successful {result=!r}',
                'logfire.lineno': 57,
                'logfire.filename': 'src/packages/logfire/logfire/integrations/pydantic_plugin.py',
            },
        },
        {
            'name': 'pydantic.validate_python',
            'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
            'parent': None,
            'start_time': 1,
            'end_time': 3,
            'attributes': {'logfire.log_type': 'real_span'},
        },
    ]


def test_pydantic_plugin_python_error(logfire: Logfire, exporter: TestExporter, mocker) -> None:
    mocker.patch('logfire.integrations.pydantic_plugin.logfire', new=logfire)

    class MyModel(BaseModel):
        x: int

    with pytest.raises(ValidationError):
        MyModel(x='a')

    # insert_assert(exporter.exported_spans_as_dict(full_attributes=True))
    assert exporter.exported_spans_as_dict(full_attributes=True) == [
        {
            'name': 'Pydantic MyModel validate_python',
            'context': {'trace_id': 1, 'span_id': 2, 'is_remote': False},
            'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
            'start_time': 1,
            'end_time': 1,
            'attributes': {
                'logfire.log_type': 'start_span',
                'logfire.msg_template': 'Pydantic {schema_name} {validation_method}',
                'schema_name': 'MyModel',
                'validation_method': 'validate_python',
                'input_data__JSON': '{"x":"a"}',
                'span_name': 'pydantic.validate_python',
            },
        },
        {
            'name': '1 validation error',
            'context': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
            'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
            'start_time': 2,
            'end_time': 2,
            'attributes': {
                'error_count': 1,
                'plural': '',
                'errors__JSON': IsJson(
                    [
                        {
                            'type': 'int_parsing',
                            'loc': ['x'],
                            'msg': 'Input should be a valid integer, unable to parse string as an integer',
                            'input': 'a',
                        }
                    ]
                ),
                'logfire.log_type': 'log',
                'logfire.level': 'warning',
                'logfire.msg_template': '{error_count} validation error{plural}',
                'logfire.lineno': 63,
                'logfire.filename': 'src/packages/logfire/logfire/integrations/pydantic_plugin.py',
            },
        },
        {
            'name': 'pydantic.validate_python',
            'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
            'parent': None,
            'start_time': 1,
            'end_time': 3,
            'attributes': {'logfire.log_type': 'real_span'},
        },
    ]


def test_pydantic_plugin_json_success(logfire: Logfire, exporter: TestExporter, mocker) -> None:
    mocker.patch('logfire.integrations.pydantic_plugin.logfire', new=logfire)

    class MyModel(BaseModel):
        x: int

    MyModel.model_validate_json('{"x":1}')

    # insert_assert(exporter.exported_spans_as_dict(full_attributes=True))
    assert exporter.exported_spans_as_dict(full_attributes=True) == [
        {
            'name': 'Pydantic MyModel validate_json',
            'context': {'trace_id': 1, 'span_id': 2, 'is_remote': False},
            'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
            'start_time': 1,
            'end_time': 1,
            'attributes': {
                'logfire.log_type': 'start_span',
                'logfire.msg_template': 'Pydantic {schema_name} {validation_method}',
                'schema_name': 'MyModel',
                'validation_method': 'validate_json',
                'input_data': '{"x":1}',
                'span_name': 'pydantic.validate_json',
            },
        },
        {
            'name': 'Validation successful result=MyModel(x=1)',
            'context': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
            'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
            'start_time': 2,
            'end_time': 2,
            'attributes': {
                'result__JSON': '{"$__datatype__":"BaseModel","data":{"x":1},"cls":"MyModel"}',
                'logfire.log_type': 'log',
                'logfire.level': 'debug',
                'logfire.msg_template': 'Validation successful {result=!r}',
                'logfire.lineno': 57,
                'logfire.filename': 'src/packages/logfire/logfire/integrations/pydantic_plugin.py',
            },
        },
        {
            'name': 'pydantic.validate_json',
            'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
            'parent': None,
            'start_time': 1,
            'end_time': 3,
            'attributes': {'logfire.log_type': 'real_span'},
        },
    ]


def test_pydantic_plugin_json_error(logfire: Logfire, exporter: TestExporter, mocker) -> None:
    mocker.patch('logfire.integrations.pydantic_plugin.logfire', new=logfire)

    class MyModel(BaseModel):
        x: int

    with pytest.raises(ValidationError):
        MyModel.model_validate({'x': 'a'})

    # insert_assert(exporter.exported_spans_as_dict(full_attributes=True))
    assert exporter.exported_spans_as_dict(full_attributes=True) == [
        {
            'name': 'Pydantic MyModel validate_python',
            'context': {'trace_id': 1, 'span_id': 2, 'is_remote': False},
            'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
            'start_time': 1,
            'end_time': 1,
            'attributes': {
                'logfire.log_type': 'start_span',
                'logfire.msg_template': 'Pydantic {schema_name} {validation_method}',
                'schema_name': 'MyModel',
                'validation_method': 'validate_python',
                'input_data__JSON': '{"x":"a"}',
                'span_name': 'pydantic.validate_python',
            },
        },
        {
            'name': '1 validation error',
            'context': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
            'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
            'start_time': 2,
            'end_time': 2,
            'attributes': {
                'error_count': 1,
                'plural': '',
                'errors__JSON': IsJson(
                    [
                        {
                            'type': 'int_parsing',
                            'loc': ['x'],
                            'msg': 'Input should be a valid integer, unable to parse string as an integer',
                            'input': 'a',
                        }
                    ]
                ),
                'logfire.log_type': 'log',
                'logfire.level': 'warning',
                'logfire.msg_template': '{error_count} validation error{plural}',
                'logfire.lineno': 63,
                'logfire.filename': 'src/packages/logfire/logfire/integrations/pydantic_plugin.py',
            },
        },
        {
            'name': 'pydantic.validate_python',
            'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
            'parent': None,
            'start_time': 1,
            'end_time': 3,
            'attributes': {'logfire.log_type': 'real_span'},
        },
    ]


def test_pydantic_plugin_strings_success(logfire: Logfire, exporter: TestExporter, mocker) -> None:
    mocker.patch('logfire.integrations.pydantic_plugin.logfire', new=logfire)

    class MyModel(BaseModel):
        x: int

    MyModel.model_validate_strings({'x': '1'}, strict=True)

    # insert_assert(exporter.exported_spans_as_dict(full_attributes=True))
    assert exporter.exported_spans_as_dict(full_attributes=True) == [
        {
            'name': 'Pydantic MyModel validate_strings',
            'context': {'trace_id': 1, 'span_id': 2, 'is_remote': False},
            'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
            'start_time': 1,
            'end_time': 1,
            'attributes': {
                'logfire.log_type': 'start_span',
                'logfire.msg_template': 'Pydantic {schema_name} {validation_method}',
                'schema_name': 'MyModel',
                'validation_method': 'validate_strings',
                'input_data__JSON': '{"x":"1"}',
                'span_name': 'pydantic.validate_strings',
            },
        },
        {
            'name': 'Validation successful result=MyModel(x=1)',
            'context': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
            'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
            'start_time': 2,
            'end_time': 2,
            'attributes': {
                'result__JSON': '{"$__datatype__":"BaseModel","data":{"x":1},"cls":"MyModel"}',
                'logfire.log_type': 'log',
                'logfire.level': 'debug',
                'logfire.msg_template': 'Validation successful {result=!r}',
                'logfire.lineno': 57,
                'logfire.filename': 'src/packages/logfire/logfire/integrations/pydantic_plugin.py',
            },
        },
        {
            'name': 'pydantic.validate_strings',
            'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
            'parent': None,
            'start_time': 1,
            'end_time': 3,
            'attributes': {'logfire.log_type': 'real_span'},
        },
    ]


def test_pydantic_plugin_strings_error(logfire: Logfire, exporter: TestExporter, mocker) -> None:
    mocker.patch('logfire.integrations.pydantic_plugin.logfire', new=logfire)

    class MyModel(BaseModel):
        x: int

    with pytest.raises(ValidationError):
        MyModel.model_validate_strings({'x': 'a'})

    # insert_assert(exporter.exported_spans_as_dict(full_attributes=True))
    assert exporter.exported_spans_as_dict(full_attributes=True) == [
        {
            'name': 'Pydantic MyModel validate_strings',
            'context': {'trace_id': 1, 'span_id': 2, 'is_remote': False},
            'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
            'start_time': 1,
            'end_time': 1,
            'attributes': {
                'logfire.log_type': 'start_span',
                'logfire.msg_template': 'Pydantic {schema_name} {validation_method}',
                'schema_name': 'MyModel',
                'validation_method': 'validate_strings',
                'input_data__JSON': '{"x":"a"}',
                'span_name': 'pydantic.validate_strings',
            },
        },
        {
            'name': '1 validation error',
            'context': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
            'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
            'start_time': 2,
            'end_time': 2,
            'attributes': {
                'error_count': 1,
                'plural': '',
                'errors__JSON': IsJson(
                    [
                        {
                            'type': 'int_parsing',
                            'loc': ['x'],
                            'msg': 'Input should be a valid integer, unable to parse string as an integer',
                            'input': 'a',
                        }
                    ]
                ),
                'logfire.log_type': 'log',
                'logfire.level': 'warning',
                'logfire.msg_template': '{error_count} validation error{plural}',
                'logfire.lineno': 63,
                'logfire.filename': 'src/packages/logfire/logfire/integrations/pydantic_plugin.py',
            },
        },
        {
            'name': 'pydantic.validate_strings',
            'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
            'parent': None,
            'start_time': 1,
            'end_time': 3,
            'attributes': {'logfire.log_type': 'real_span'},
        },
    ]
