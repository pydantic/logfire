import json
import warnings
from datetime import datetime
from decimal import Decimal

import pydantic
import pytest
from pydantic import AnyUrl, BaseModel, ConfigDict, Field

import logfire
from logfire._internal.utils import get_version
from logfire.testing import TestExporter


@pytest.mark.parametrize('serialize_by_alias', [False, True])
def test_pydantic_model_schema_matches_serialized_aliases(exporter: TestExporter, serialize_by_alias: bool) -> None:
    class NestedAliasModel(BaseModel):
        model_config = ConfigDict(serialize_by_alias=serialize_by_alias)

        nested_url: AnyUrl = Field(serialization_alias='nested_output')

    class AliasedModel(BaseModel):
        model_config = ConfigDict(
            serialize_by_alias=serialize_by_alias,
            alias_generator=lambda name: name.upper(),
            populate_by_name=True,
            extra='allow',
        )

        explicit_url: AnyUrl = Field(alias='input_url', serialization_alias='output_url')
        alias_only_url: AnyUrl = Field(alias='input_and_output_url')
        generated_url: AnyUrl
        nested: NestedAliasModel
        hidden_url: AnyUrl = Field(repr=False)

    model = AliasedModel.model_validate(
        {
            'explicit_url': 'https://example.com/explicit',
            'alias_only_url': 'https://example.com/alias-only',
            'generated_url': 'https://example.com/generated',
            'nested': {'nested_url': 'https://example.com/nested'},
            'hidden_url': 'https://example.com/hidden',
            'extra_url': AnyUrl('https://example.com/extra'),
        }
    )
    logfire.info('aliased model {model}', model=model)

    attributes = exporter.exported_spans[0].attributes
    assert attributes is not None
    recorded_json = attributes['model']
    schema_json = attributes['logfire.json_schema']
    assert isinstance(recorded_json, str)
    assert isinstance(schema_json, str)
    recorded = json.loads(recorded_json)
    schema = json.loads(schema_json)['properties']['model']
    uses_aliases = serialize_by_alias and get_version(pydantic.__version__) >= get_version('2.11')
    explicit_key = 'output_url' if uses_aliases else 'explicit_url'
    alias_only_key = 'input_and_output_url' if uses_aliases else 'alias_only_url'
    generated_key = 'GENERATED_URL' if uses_aliases else 'generated_url'
    nested_key = 'NESTED' if uses_aliases else 'nested'
    nested_url_key = 'nested_output' if uses_aliases else 'nested_url'
    url_schema = {'type': 'string', 'x-python-datatype': type(AnyUrl('https://example.com')).__name__}

    assert recorded == {
        explicit_key: 'https://example.com/explicit',
        alias_only_key: 'https://example.com/alias-only',
        generated_key: 'https://example.com/generated',
        nested_key: {nested_url_key: 'https://example.com/nested'},
        'extra_url': 'https://example.com/extra',
    }
    assert schema == {
        'type': 'object',
        'title': 'AliasedModel',
        'x-python-datatype': 'PydanticModel',
        'properties': {
            explicit_key: url_schema,
            alias_only_key: url_schema,
            generated_key: url_schema,
            nested_key: {
                'type': 'object',
                'title': 'NestedAliasModel',
                'x-python-datatype': 'PydanticModel',
                'properties': {nested_url_key: url_schema},
            },
            'extra_url': url_schema,
        },
    }


@pytest.mark.parametrize('serialize_by_alias', [False, True])
def test_serialization_alias_matches_another_field_name(exporter: TestExporter, serialize_by_alias: bool) -> None:
    class AliasedModel(BaseModel):
        model_config = ConfigDict(serialize_by_alias=serialize_by_alias)

        first: datetime = Field(serialization_alias='second')
        second: Decimal = Field(serialization_alias='total')

    model = AliasedModel.model_validate({'first': '2024-01-02T03:04:05', 'second': '1.25'})
    logfire.info('aliased model {model}', model=model)

    attributes = exporter.exported_spans[0].attributes
    assert attributes is not None
    recorded_json = attributes['model']
    schema_json = attributes['logfire.json_schema']
    assert isinstance(recorded_json, str)
    assert isinstance(schema_json, str)
    recorded = json.loads(recorded_json)
    schema = json.loads(schema_json)['properties']['model']
    uses_aliases = serialize_by_alias and get_version(pydantic.__version__) >= get_version('2.11')
    date_key = 'second' if uses_aliases else 'first'
    decimal_key = 'total' if uses_aliases else 'second'

    assert recorded == {date_key: '2024-01-02T03:04:05', decimal_key: '1.25'}
    assert schema == {
        'type': 'object',
        'title': 'AliasedModel',
        'x-python-datatype': 'PydanticModel',
        'properties': {
            date_key: {'type': 'string', 'format': 'date-time', 'x-python-datatype': 'datetime'},
            decimal_key: {'type': 'string', 'format': 'decimal', 'x-python-datatype': 'Decimal'},
        },
    }


def test_alias_detection_does_not_serialize_hidden_fields(exporter: TestExporter) -> None:
    class AliasedModel(BaseModel):
        model_config = ConfigDict(serialize_by_alias=True)

        url: AnyUrl = Field(serialization_alias='output_url')
        password: str = Field(repr=False)

    model = AliasedModel.model_validate({'url': 'https://example.com', 'password': 'original'})
    model = model.model_copy(update={'password': b'secret'})
    with warnings.catch_warnings(record=True) as recorded_warnings:
        warnings.simplefilter('always')
        logfire.info('aliased model {model}', model=model)

    assert recorded_warnings == []
    attributes = exporter.exported_spans[0].attributes
    assert attributes is not None
    recorded_json = attributes['model']
    assert isinstance(recorded_json, str)
    assert 'secret' not in recorded_json
    assert 'password' not in recorded_json


def test_empty_serialization_alias(exporter: TestExporter) -> None:
    class AliasedModel(BaseModel):
        model_config = ConfigDict(serialize_by_alias=True)

        url: AnyUrl = Field(serialization_alias='')

    model = AliasedModel.model_validate({'url': 'https://example.com'})
    logfire.info('aliased model {model}', model=model)

    attributes = exporter.exported_spans[0].attributes
    assert attributes is not None
    recorded_json = attributes['model']
    schema_json = attributes['logfire.json_schema']
    assert isinstance(recorded_json, str)
    assert isinstance(schema_json, str)
    serialized_key = '' if get_version(pydantic.__version__) >= get_version('2.11') else 'url'
    assert json.loads(recorded_json) == {serialized_key: 'https://example.com/'}
    assert json.loads(schema_json)['properties']['model'] == {
        'type': 'object',
        'title': 'AliasedModel',
        'x-python-datatype': 'PydanticModel',
        'properties': {serialized_key: {'type': 'string', 'x-python-datatype': type(model.url).__name__}},
    }


def test_excluded_alias_does_not_hide_alias_setting(exporter: TestExporter) -> None:
    class AliasedModel(BaseModel):
        model_config = ConfigDict(serialize_by_alias=True)

        excluded_url: AnyUrl = Field(serialization_alias='excluded_output', exclude=True)
        visible_url: AnyUrl = Field(serialization_alias='visible_output')

    model = AliasedModel.model_validate(
        {'excluded_url': 'https://example.com/excluded', 'visible_url': 'https://example.com/visible'}
    )
    logfire.info('aliased model {model}', model=model)

    attributes = exporter.exported_spans[0].attributes
    assert attributes is not None
    recorded_json = attributes['model']
    schema_json = attributes['logfire.json_schema']
    assert isinstance(recorded_json, str)
    assert isinstance(schema_json, str)
    serialized_key = 'visible_output' if get_version(pydantic.__version__) >= get_version('2.11') else 'visible_url'
    assert json.loads(recorded_json) == {serialized_key: 'https://example.com/visible'}
    schema_properties = json.loads(schema_json)['properties']['model']['properties']
    assert schema_properties[serialized_key] == {
        'type': 'string',
        'x-python-datatype': type(model.visible_url).__name__,
    }
