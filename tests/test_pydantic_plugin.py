from __future__ import annotations

import importlib.metadata

import pytest
from pydantic import BaseModel, ValidationError
from pydantic.plugin import SchemaTypePath
from pydantic_core import core_schema

import logfire
from logfire.integrations.pydantic_plugin import LogfirePydanticPlugin
from logfire.testing import TestExporter


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
    logfire.configure(disable_pydantic_plugin=True, send_to_logfire=False)
    plugin = LogfirePydanticPlugin()
    assert plugin.new_schema_validator(
        core_schema.int_schema(), None, SchemaTypePath(module='', name=''), 'BaseModel', None, {}
    ) == (None, None, None)


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
    logfire.configure(send_to_logfire=False, pydantic_plugin_include=include, pydantic_plugin_exclude=exclude)
    plugin = LogfirePydanticPlugin()

    result = plugin.new_schema_validator(
        core_schema.int_schema(), None, SchemaTypePath(module=module, name=name), 'BaseModel', None, {}
    )
    if expected_to_include:
        assert result != (None, None, None)
    else:
        assert result == (None, None, None)


def test_pydantic_plugin_python_success(exporter: TestExporter) -> None:
    class MyModel(BaseModel):
        x: int

    MyModel(x=1)

    # insert_assert(exporter.exported_spans_as_dict(_include_start_spans=True))
    assert exporter.exported_spans_as_dict(_include_start_spans=True) == [
        {
            'name': 'pydantic.validate_python (start)',
            'context': {'trace_id': 1, 'span_id': 2, 'is_remote': False},
            'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
            'start_time': 1000000000,
            'end_time': 1000000000,
            'attributes': {
                'code.filepath': 'pydantic_plugin.py',
                'code.lineno': 123,
                'code.function': '_on_enter',
                'schema_name': 'MyModel',
                'validation_method': 'validate_python',
                'input_data__JSON': '{"x":1}',
                'logfire.msg_template': 'Pydantic {schema_name} {validation_method}',
                'logfire.msg': 'Pydantic MyModel validate_python',
                'logfire.span_type': 'start_span',
                'logfire.start_parent_id': '0',
            },
        },
        {
            'name': 'Validation successful result=MyModel(x=1)',
            'context': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
            'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
            'start_time': 2000000000,
            'end_time': 2000000000,
            'attributes': {
                'logfire.span_type': 'log',
                'logfire.level': 'debug',
                'logfire.msg_template': 'Validation successful {result=!r}',
                'logfire.msg': 'Validation successful result=MyModel(x=1)',
                'code.filepath': 'pydantic_plugin.py',
                'code.lineno': 123,
                'code.function': 'on_success',
                'result__JSON': '{"$__datatype__":"BaseModel","data":{"x":1},"cls":"MyModel"}',
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
                'code.lineno': 123,
                'code.function': '_on_enter',
                'schema_name': 'MyModel',
                'validation_method': 'validate_python',
                'input_data__JSON': '{"x":1}',
                'logfire.msg_template': 'Pydantic {schema_name} {validation_method}',
                'logfire.msg': 'Pydantic MyModel validate_python',
                'logfire.span_type': 'span',
            },
        },
    ]


def test_pydantic_plugin_python_error(exporter: TestExporter) -> None:
    class MyModel(BaseModel):
        x: int

    with pytest.raises(ValidationError):
        MyModel(x='a')  # type: ignore

    # insert_assert(exporter.exported_spans_as_dict(_include_start_spans=True))
    assert exporter.exported_spans_as_dict(_include_start_spans=True) == [
        {
            'name': 'pydantic.validate_python (start)',
            'context': {'trace_id': 1, 'span_id': 2, 'is_remote': False},
            'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
            'start_time': 1000000000,
            'end_time': 1000000000,
            'attributes': {
                'code.filepath': 'pydantic_plugin.py',
                'code.lineno': 123,
                'code.function': '_on_enter',
                'schema_name': 'MyModel',
                'validation_method': 'validate_python',
                'input_data__JSON': '{"x":"a"}',
                'logfire.msg_template': 'Pydantic {schema_name} {validation_method}',
                'logfire.msg': 'Pydantic MyModel validate_python',
                'logfire.span_type': 'start_span',
                'logfire.start_parent_id': '0',
            },
        },
        {
            'name': '1 validation error',
            'context': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
            'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
            'start_time': 2000000000,
            'end_time': 2000000000,
            'attributes': {
                'logfire.span_type': 'log',
                'logfire.level': 'warning',
                'logfire.msg_template': '{error_count} validation error{plural}',
                'logfire.msg': '1 validation error',
                'code.filepath': 'pydantic_plugin.py',
                'code.lineno': 123,
                'code.function': 'on_error',
                'error_count': 1,
                'plural': '',
                'errors__JSON': '[{"type":"int_parsing","loc":["x"],"msg":"Input should be a valid integer, unable to parse string as an integer","input":"a"}]',
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
                'code.lineno': 123,
                'code.function': '_on_enter',
                'schema_name': 'MyModel',
                'validation_method': 'validate_python',
                'input_data__JSON': '{"x":"a"}',
                'logfire.msg_template': 'Pydantic {schema_name} {validation_method}',
                'logfire.msg': 'Pydantic MyModel validate_python',
                'logfire.span_type': 'span',
            },
        },
    ]


def test_pydantic_plugin_json_success(exporter: TestExporter) -> None:
    class MyModel(BaseModel):
        x: int

    MyModel.model_validate_json('{"x":1}')

    # insert_assert(exporter.exported_spans_as_dict(_include_start_spans=True))
    assert exporter.exported_spans_as_dict(_include_start_spans=True) == [
        {
            'name': 'pydantic.validate_json (start)',
            'context': {'trace_id': 1, 'span_id': 2, 'is_remote': False},
            'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
            'start_time': 1000000000,
            'end_time': 1000000000,
            'attributes': {
                'code.filepath': 'pydantic_plugin.py',
                'code.lineno': 123,
                'code.function': '_on_enter',
                'schema_name': 'MyModel',
                'validation_method': 'validate_json',
                'input_data': '{"x":1}',
                'logfire.msg_template': 'Pydantic {schema_name} {validation_method}',
                'logfire.msg': 'Pydantic MyModel validate_json',
                'logfire.span_type': 'start_span',
                'logfire.start_parent_id': '0',
            },
        },
        {
            'name': 'Validation successful result=MyModel(x=1)',
            'context': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
            'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
            'start_time': 2000000000,
            'end_time': 2000000000,
            'attributes': {
                'logfire.span_type': 'log',
                'logfire.level': 'debug',
                'logfire.msg_template': 'Validation successful {result=!r}',
                'logfire.msg': 'Validation successful result=MyModel(x=1)',
                'code.filepath': 'pydantic_plugin.py',
                'code.lineno': 123,
                'code.function': 'on_success',
                'result__JSON': '{"$__datatype__":"BaseModel","data":{"x":1},"cls":"MyModel"}',
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
                'code.lineno': 123,
                'code.function': '_on_enter',
                'schema_name': 'MyModel',
                'validation_method': 'validate_json',
                'input_data': '{"x":1}',
                'logfire.msg_template': 'Pydantic {schema_name} {validation_method}',
                'logfire.msg': 'Pydantic MyModel validate_json',
                'logfire.span_type': 'span',
            },
        },
    ]


def test_pydantic_plugin_json_error(exporter: TestExporter) -> None:
    class MyModel(BaseModel):
        x: int

    with pytest.raises(ValidationError):
        MyModel.model_validate({'x': 'a'})

    # insert_assert(exporter.exported_spans_as_dict(_include_start_spans=True))
    assert exporter.exported_spans_as_dict(_include_start_spans=True) == [
        {
            'name': 'pydantic.validate_python (start)',
            'context': {'trace_id': 1, 'span_id': 2, 'is_remote': False},
            'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
            'start_time': 1000000000,
            'end_time': 1000000000,
            'attributes': {
                'code.filepath': 'pydantic_plugin.py',
                'code.lineno': 123,
                'code.function': '_on_enter',
                'schema_name': 'MyModel',
                'validation_method': 'validate_python',
                'input_data__JSON': '{"x":"a"}',
                'logfire.msg_template': 'Pydantic {schema_name} {validation_method}',
                'logfire.msg': 'Pydantic MyModel validate_python',
                'logfire.span_type': 'start_span',
                'logfire.start_parent_id': '0',
            },
        },
        {
            'name': '1 validation error',
            'context': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
            'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
            'start_time': 2000000000,
            'end_time': 2000000000,
            'attributes': {
                'logfire.span_type': 'log',
                'logfire.level': 'warning',
                'logfire.msg_template': '{error_count} validation error{plural}',
                'logfire.msg': '1 validation error',
                'code.filepath': 'pydantic_plugin.py',
                'code.lineno': 123,
                'code.function': 'on_error',
                'error_count': 1,
                'plural': '',
                'errors__JSON': '[{"type":"int_parsing","loc":["x"],"msg":"Input should be a valid integer, unable to parse string as an integer","input":"a"}]',
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
                'code.lineno': 123,
                'code.function': '_on_enter',
                'schema_name': 'MyModel',
                'validation_method': 'validate_python',
                'input_data__JSON': '{"x":"a"}',
                'logfire.msg_template': 'Pydantic {schema_name} {validation_method}',
                'logfire.msg': 'Pydantic MyModel validate_python',
                'logfire.span_type': 'span',
            },
        },
    ]


def test_pydantic_plugin_strings_success(exporter: TestExporter) -> None:
    class MyModel(BaseModel):
        x: int

    MyModel.model_validate_strings({'x': '1'}, strict=True)

    # insert_assert(exporter.exported_spans_as_dict(_include_start_spans=True))
    assert exporter.exported_spans_as_dict(_include_start_spans=True) == [
        {
            'name': 'pydantic.validate_strings (start)',
            'context': {'trace_id': 1, 'span_id': 2, 'is_remote': False},
            'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
            'start_time': 1000000000,
            'end_time': 1000000000,
            'attributes': {
                'code.filepath': 'pydantic_plugin.py',
                'code.lineno': 123,
                'code.function': '_on_enter',
                'schema_name': 'MyModel',
                'validation_method': 'validate_strings',
                'input_data__JSON': '{"x":"1"}',
                'logfire.msg_template': 'Pydantic {schema_name} {validation_method}',
                'logfire.msg': 'Pydantic MyModel validate_strings',
                'logfire.span_type': 'start_span',
                'logfire.start_parent_id': '0',
            },
        },
        {
            'name': 'Validation successful result=MyModel(x=1)',
            'context': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
            'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
            'start_time': 2000000000,
            'end_time': 2000000000,
            'attributes': {
                'logfire.span_type': 'log',
                'logfire.level': 'debug',
                'logfire.msg_template': 'Validation successful {result=!r}',
                'logfire.msg': 'Validation successful result=MyModel(x=1)',
                'code.filepath': 'pydantic_plugin.py',
                'code.lineno': 123,
                'code.function': 'on_success',
                'result__JSON': '{"$__datatype__":"BaseModel","data":{"x":1},"cls":"MyModel"}',
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
                'code.lineno': 123,
                'code.function': '_on_enter',
                'schema_name': 'MyModel',
                'validation_method': 'validate_strings',
                'input_data__JSON': '{"x":"1"}',
                'logfire.msg_template': 'Pydantic {schema_name} {validation_method}',
                'logfire.msg': 'Pydantic MyModel validate_strings',
                'logfire.span_type': 'span',
            },
        },
    ]


def test_pydantic_plugin_strings_error(exporter: TestExporter) -> None:
    class MyModel(BaseModel):
        x: int

    with pytest.raises(ValidationError):
        MyModel.model_validate_strings({'x': 'a'})

    # insert_assert(exporter.exported_spans_as_dict(_include_start_spans=True))
    assert exporter.exported_spans_as_dict(_include_start_spans=True) == [
        {
            'name': 'pydantic.validate_strings (start)',
            'context': {'trace_id': 1, 'span_id': 2, 'is_remote': False},
            'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
            'start_time': 1000000000,
            'end_time': 1000000000,
            'attributes': {
                'code.filepath': 'pydantic_plugin.py',
                'code.lineno': 123,
                'code.function': '_on_enter',
                'schema_name': 'MyModel',
                'validation_method': 'validate_strings',
                'input_data__JSON': '{"x":"a"}',
                'logfire.msg_template': 'Pydantic {schema_name} {validation_method}',
                'logfire.msg': 'Pydantic MyModel validate_strings',
                'logfire.span_type': 'start_span',
                'logfire.start_parent_id': '0',
            },
        },
        {
            'name': '1 validation error',
            'context': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
            'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
            'start_time': 2000000000,
            'end_time': 2000000000,
            'attributes': {
                'logfire.span_type': 'log',
                'logfire.level': 'warning',
                'logfire.msg_template': '{error_count} validation error{plural}',
                'logfire.msg': '1 validation error',
                'code.filepath': 'pydantic_plugin.py',
                'code.lineno': 123,
                'code.function': 'on_error',
                'error_count': 1,
                'plural': '',
                'errors__JSON': '[{"type":"int_parsing","loc":["x"],"msg":"Input should be a valid integer, unable to parse string as an integer","input":"a"}]',
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
                'code.lineno': 123,
                'code.function': '_on_enter',
                'schema_name': 'MyModel',
                'validation_method': 'validate_strings',
                'input_data__JSON': '{"x":"a"}',
                'logfire.msg_template': 'Pydantic {schema_name} {validation_method}',
                'logfire.msg': 'Pydantic MyModel validate_strings',
                'logfire.span_type': 'span',
            },
        },
    ]
