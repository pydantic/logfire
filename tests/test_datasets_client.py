"""Tests for logfire.experimental.datasets client achieving 100% coverage."""

# pyright: reportPrivateUsage=false, reportArgumentType=false, reportUnknownVariableType=false

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from unittest.mock import patch

import httpx
import pytest
from pydantic import BaseModel

try:
    from pydantic_evals import Case
except (ImportError, AttributeError):
    pytest.skip('pydantic_evals not compatible with this environment', allow_module_level=True)

from logfire.experimental.datasets import (
    AsyncLogfireAPIClient,
    CaseNotFoundError,
    DatasetApiError,
    DatasetNotFoundError,
    LogfireAPIClient,
)
from logfire.experimental.datasets.client import (
    _import_pydantic_evals,
    _serialize_case,
    _serialize_evaluators,
    _serialize_value,
    _type_to_schema,
)

# --- Test types ---


@dataclass
class MyInput:
    question: str


@dataclass
class MyOutput:
    answer: str


@dataclass
class MyMetadata:
    source: str


class PydanticInput(BaseModel):
    question: str


# --- Mock transport helpers ---

FAKE_DATASET = {
    'id': 'ds-123',
    'name': 'test-dataset',
    'description': 'A test dataset',
    'case_count': 0,
}

FAKE_CASE = {
    'id': 'case-456',
    'name': 'test-case',
    'inputs': {'question': 'What is 2+2?'},
    'expected_output': {'answer': '4'},
}

FAKE_EXPORT = {
    'name': 'test-dataset',
    'cases': [
        {
            'name': 'test-case',
            'inputs': {'question': 'What is 2+2?'},
            'expected_output': {'answer': '4'},
        }
    ],
}


def make_mock_transport(responses: dict[tuple[str, str], httpx.Response | None] | None = None) -> httpx.MockTransport:
    """Create a mock transport that maps (method, path) -> response."""
    default_responses: dict[tuple[str, str], httpx.Response] = {
        ('GET', '/v1/datasets/'): httpx.Response(200, json=[FAKE_DATASET]),
        ('GET', '/v1/datasets/test-dataset/'): httpx.Response(200, json=FAKE_DATASET),
        ('POST', '/v1/datasets/'): httpx.Response(200, json=FAKE_DATASET),
        ('PUT', '/v1/datasets/test-dataset/'): httpx.Response(200, json=FAKE_DATASET),
        ('DELETE', '/v1/datasets/test-dataset/'): httpx.Response(204),
        ('GET', '/v1/datasets/test-dataset/cases/'): httpx.Response(200, json=[FAKE_CASE]),
        ('GET', '/v1/datasets/test-dataset/cases/case-456/'): httpx.Response(200, json=FAKE_CASE),
        ('POST', '/v1/datasets/test-dataset/cases/bulk/'): httpx.Response(200, json=[FAKE_CASE]),
        ('POST', '/v1/datasets/test-dataset/import/'): httpx.Response(200, json=[FAKE_CASE]),
        ('PUT', '/v1/datasets/test-dataset/cases/case-456/'): httpx.Response(200, json=FAKE_CASE),
        ('DELETE', '/v1/datasets/test-dataset/cases/case-456/'): httpx.Response(204),
        ('GET', '/v1/datasets/test-dataset/export/'): httpx.Response(200, json=FAKE_EXPORT),
    }

    if responses:
        default_responses.update(responses)  # type: ignore

    all_responses = default_responses

    def handler(request: httpx.Request) -> httpx.Response:
        # Match on method and path (without query string)
        key = (request.method, request.url.path)
        if key in all_responses:
            return all_responses[key]
        return httpx.Response(404, json={'detail': 'Not found'})

    return httpx.MockTransport(handler)


def make_client(
    responses: dict[tuple[str, str], httpx.Response | None] | None = None,
) -> LogfireAPIClient:
    transport = make_mock_transport(responses)
    return LogfireAPIClient(
        client=httpx.Client(transport=transport, base_url='https://test.logfire.dev'),
    )


def make_async_client(
    responses: dict[tuple[str, str], httpx.Response | None] | None = None,
) -> AsyncLogfireAPIClient:
    transport = make_mock_transport(responses)
    return AsyncLogfireAPIClient(
        client=httpx.AsyncClient(transport=transport, base_url='https://test.logfire.dev'),
    )


# =============================================================================
# Helper function tests
# =============================================================================


class TestTypeToSchema:
    def test_none_returns_none(self):
        assert _type_to_schema(None) is None

    def test_dataclass(self):
        schema = _type_to_schema(MyInput)
        assert schema is not None
        assert schema['type'] == 'object'
        assert 'question' in schema['properties']

    def test_pydantic_model(self):
        schema = _type_to_schema(PydanticInput)
        assert schema is not None
        assert 'question' in schema['properties']


class TestSerializeValue:
    def test_none_returns_none(self):
        assert _serialize_value(None) is None

    def test_dataclass(self):
        result = _serialize_value(MyInput(question='hello'))
        assert result == {'question': 'hello'}

    def test_pydantic_model(self):
        result = _serialize_value(PydanticInput(question='hello'))
        assert result == {'question': 'hello'}


class TestSerializeEvaluators:
    def test_pydantic_model_evaluator(self):
        class MyEvaluator(BaseModel):
            threshold: float = 0.5

            @classmethod
            def get_serialization_name(cls) -> str:
                return 'MyEval'

        result = _serialize_evaluators([MyEvaluator(threshold=0.8)])
        assert result == [{'name': 'MyEval', 'arguments': {'threshold': 0.8}}]

    def test_dataclass_evaluator(self):
        @dataclass
        class MyEvaluator:
            threshold: float = 0.5

        result = _serialize_evaluators([MyEvaluator(threshold=0.8)])
        assert result == [{'name': 'MyEvaluator', 'arguments': {'threshold': 0.8}}]

    def test_plain_object_evaluator(self):
        """An evaluator without model_dump or __dataclass_fields__ should have arguments=None."""

        class SimpleEval:
            pass

        result = _serialize_evaluators([SimpleEval()])
        assert result == [{'name': 'SimpleEval', 'arguments': None}]

    def test_empty_arguments_become_none(self):
        """An evaluator with no fields should serialize arguments as None."""

        @dataclass
        class EmptyEval:
            pass

        result = _serialize_evaluators([EmptyEval()])
        assert result == [{'name': 'EmptyEval', 'arguments': None}]

    def test_evaluator_with_get_serialization_name(self):
        @dataclass
        class CustomNameEval:
            @classmethod
            def get_serialization_name(cls) -> str:
                return 'custom-name'

        result = _serialize_evaluators([CustomNameEval()])
        assert result == [{'name': 'custom-name', 'arguments': None}]

    def test_evaluator_without_get_serialization_name(self):
        """Falls back to __name__ when get_serialization_name is not defined."""

        @dataclass
        class FallbackEval:
            score: float = 1.0

        result = _serialize_evaluators([FallbackEval()])
        assert result == [{'name': 'FallbackEval', 'arguments': {'score': 1.0}}]


class TestSerializeCase:
    def test_minimal_case(self):
        case: Case[MyInput, MyOutput, Any] = Case(inputs=MyInput(question='hi'))
        result = _serialize_case(case)
        assert result == {'inputs': {'question': 'hi'}}

    def test_full_case(self):
        @dataclass
        class MyEval:
            pass

        case: Case[MyInput, MyOutput, MyMetadata] = Case(
            name='test',
            inputs=MyInput(question='hi'),
            expected_output=MyOutput(answer='hello'),
            metadata=MyMetadata(source='manual'),
            evaluators=[MyEval()],
        )
        result = _serialize_case(case)
        assert result == {
            'name': 'test',
            'inputs': {'question': 'hi'},
            'expected_output': {'answer': 'hello'},
            'metadata': {'source': 'manual'},
            'evaluators': [{'name': 'MyEval', 'arguments': None}],
        }

    def test_dict_inputs(self):
        case: Case[dict[str, str], dict[str, str], Any] = Case(inputs={'question': 'hi'})
        result = _serialize_case(case)
        assert result == {'inputs': {'question': 'hi'}}

    def test_dict_expected_output(self):
        case: Case[dict[str, str], dict[str, str], Any] = Case(
            inputs={'q': 'hi'},
            expected_output={'a': 'hello'},
        )
        result = _serialize_case(case)
        assert result == {'inputs': {'q': 'hi'}, 'expected_output': {'a': 'hello'}}

    def test_dict_metadata(self):
        case: Case[dict[str, str], Any, dict[str, str]] = Case(
            inputs={'q': 'hi'},
            metadata={'source': 'test'},
        )
        result = _serialize_case(case)
        assert result == {'inputs': {'q': 'hi'}, 'metadata': {'source': 'test'}}


class TestImportPydanticEvals:
    def test_success(self):
        Dataset, Case_ = _import_pydantic_evals()
        from pydantic_evals import Case as RealCase, Dataset as RealDataset

        assert Dataset is RealDataset
        assert Case_ is RealCase

    def test_import_error(self):
        with patch.dict('sys.modules', {'pydantic_evals': None}):
            with pytest.raises(ImportError, match='pydantic-evals is required'):
                _import_pydantic_evals()


# =============================================================================
# Error class tests
# =============================================================================


class TestDatasetApiError:
    def test_attributes(self):
        err = DatasetApiError(422, {'detail': 'Validation error'})
        assert err.status_code == 422
        assert err.detail == {'detail': 'Validation error'}
        assert 'API error 422' in str(err)


# =============================================================================
# _handle_response tests
# =============================================================================


class TestHandleResponse:
    def _make_base_client(self):
        return make_client()

    def test_200_json(self):
        client = self._make_base_client()
        response = httpx.Response(200, json={'key': 'value'})
        assert client._handle_response(response) == {'key': 'value'}

    def test_204_returns_none(self):
        client = self._make_base_client()
        response = httpx.Response(204)
        assert client._handle_response(response) is None

    def test_404_dataset_not_found(self):
        client = self._make_base_client()
        response = httpx.Response(404, json={'detail': 'Dataset not found'})
        with pytest.raises(DatasetNotFoundError):
            client._handle_response(response)

    def test_404_case_not_found(self):
        client = self._make_base_client()
        response = httpx.Response(404, json={'detail': 'Case not found'})
        with pytest.raises(CaseNotFoundError):
            client._handle_response(response, is_case_endpoint=True)

    def test_404_case_endpoint_but_dataset_error(self):
        """When is_case_endpoint=True but response doesn't mention 'case', raise DatasetNotFoundError."""
        client = self._make_base_client()
        response = httpx.Response(404, json={'detail': 'Dataset not found'})
        with pytest.raises(DatasetNotFoundError):
            client._handle_response(response, is_case_endpoint=True)

    def test_404_empty_content(self):
        client = self._make_base_client()
        response = httpx.Response(404)
        with pytest.raises(DatasetNotFoundError, match='Not found'):
            client._handle_response(response)

    def test_400_with_json(self):
        client = self._make_base_client()
        response = httpx.Response(400, json={'detail': 'Bad request'})
        with pytest.raises(DatasetApiError) as exc_info:
            client._handle_response(response)
        assert exc_info.value.status_code == 400

    def test_500_with_text(self):
        client = self._make_base_client()
        response = httpx.Response(500, text='')
        with pytest.raises(DatasetApiError) as exc_info:
            client._handle_response(response)
        assert exc_info.value.status_code == 500

    def test_404_non_json_body(self):
        """Non-JSON 404 bodies should fall back to response text instead of raising JSONDecodeError."""
        client = self._make_base_client()
        response = httpx.Response(404, text='<html>Not Found</html>')
        with pytest.raises(DatasetNotFoundError, match='Not Found'):
            client._handle_response(response)

    def test_400_non_json_body(self):
        """Non-JSON error bodies should fall back to response text instead of raising JSONDecodeError."""
        client = self._make_base_client()
        response = httpx.Response(502, text='<html>Bad Gateway</html>')
        with pytest.raises(DatasetApiError) as exc_info:
            client._handle_response(response)
        assert exc_info.value.status_code == 502

    def test_404_case_endpoint_non_dict_response(self):
        """When is_case_endpoint=True but the 404 response is a non-dict (e.g. string), raise DatasetNotFoundError."""
        client = self._make_base_client()
        response = httpx.Response(404, text='<html>Not Found</html>')
        with pytest.raises(DatasetNotFoundError):
            client._handle_response(response, is_case_endpoint=True)


# =============================================================================
# Sync client tests
# =============================================================================


class TestLogfireAPIClient:
    def test_init_with_base_url(self):
        client = LogfireAPIClient(api_key='test-key', base_url='https://custom.url')
        assert str(client.client.base_url) == 'https://custom.url'
        client.client.close()

    def test_init_infers_base_url(self):
        client = LogfireAPIClient(api_key='pylf_v1_us_test1234567890')
        base_url = str(client.client.base_url)
        assert 'logfire' in base_url or 'pydantic' in base_url
        client.client.close()

    def test_init_with_client(self):
        httpx_client = httpx.Client(base_url='https://custom.url')
        client = LogfireAPIClient(client=httpx_client)
        assert client.client is httpx_client
        client.client.close()

    def test_init_requires_client_or_api_key(self):
        with pytest.raises(ValueError, match='Either client or api_key must be provided'):
            LogfireAPIClient()

    def test_context_manager(self):
        client = make_client()
        with client as c:
            assert c is client
        # After exiting, the underlying httpx client is closed

    def test_list_datasets(self):
        client = make_client()
        result = client.list_datasets()
        assert result == [FAKE_DATASET]

    def test_get_dataset(self):
        client = make_client()
        result = client.get_dataset('test-dataset')
        assert result == FAKE_DATASET

    def test_create_dataset_minimal(self):
        client = make_client()
        result = client.create_dataset(name='test-dataset')
        assert result == FAKE_DATASET

    def test_create_dataset_full(self):
        """Test create_dataset with all optional parameters."""
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests_seen.append(request)
            return httpx.Response(200, json=FAKE_DATASET)

        transport = httpx.MockTransport(handler)
        client = LogfireAPIClient(api_key='test-key', base_url='https://test.logfire.dev')
        client.client = httpx.Client(transport=transport, base_url='https://test.logfire.dev')

        result = client.create_dataset(
            name='test-dataset',
            input_type=MyInput,
            output_type=MyOutput,
            metadata_type=MyMetadata,
            description='A test dataset',
            guidance='Be helpful',
            ai_managed_guidance=True,
        )
        assert result == FAKE_DATASET

        body = json.loads(requests_seen[0].content)
        assert body['name'] == 'test-dataset'
        assert body['description'] == 'A test dataset'
        assert 'input_schema' in body
        assert 'output_schema' in body
        assert 'metadata_schema' in body
        assert body['guidance'] == 'Be helpful'
        assert body['ai_managed_guidance'] is True

    def test_update_dataset_minimal(self):
        """When no params change, only empty data is sent."""
        client = make_client()
        result = client.update_dataset('test-dataset')
        assert result == FAKE_DATASET

    def test_update_dataset_full(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests_seen.append(request)
            return httpx.Response(200, json=FAKE_DATASET)

        transport = httpx.MockTransport(handler)
        client = LogfireAPIClient(api_key='test-key', base_url='https://test.logfire.dev')
        client.client = httpx.Client(transport=transport, base_url='https://test.logfire.dev')

        client.update_dataset(
            'test-dataset',
            name='new-name',
            input_type=MyInput,
            output_type=MyOutput,
            metadata_type=MyMetadata,
            description='Updated desc',
            guidance='New guidance',
            ai_managed_guidance=True,
        )

        body = json.loads(requests_seen[0].content)
        assert body['name'] == 'new-name'
        assert body['description'] == 'Updated desc'
        assert 'input_schema' in body
        assert 'output_schema' in body
        assert 'metadata_schema' in body
        assert body['guidance'] == 'New guidance'
        assert body['ai_managed_guidance'] is True

    def test_update_dataset_clear_fields(self):
        """Test that passing None clears fields (using _UNSET sentinel)."""
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests_seen.append(request)
            return httpx.Response(200, json=FAKE_DATASET)

        transport = httpx.MockTransport(handler)
        client = LogfireAPIClient(api_key='test-key', base_url='https://test.logfire.dev')
        client.client = httpx.Client(transport=transport, base_url='https://test.logfire.dev')

        client.update_dataset('test-dataset', description=None, guidance=None)

        body = json.loads(requests_seen[0].content)
        assert body['description'] is None
        assert body['guidance'] is None

    def test_delete_dataset(self):
        client = make_client()
        result = client.delete_dataset('test-dataset')
        assert result is None

    def test_list_cases(self):
        client = make_client()
        result = client.list_cases('test-dataset')
        assert result == [FAKE_CASE]

    def test_list_cases_with_tags(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests_seen.append(request)
            return httpx.Response(200, json=[FAKE_CASE])

        transport = httpx.MockTransport(handler)
        client = LogfireAPIClient(api_key='test-key', base_url='https://test.logfire.dev')
        client.client = httpx.Client(transport=transport, base_url='https://test.logfire.dev')

        client.list_cases('test-dataset', tags=['tag1', 'tag2'])
        assert 'tags' in str(requests_seen[0].url)

    def test_get_case(self):
        client = make_client()
        result = client.get_case('test-dataset', 'case-456')
        assert result == FAKE_CASE

    def test_add_cases(self):
        client = make_client()
        cases: list[Case[MyInput, MyOutput, Any]] = [
            Case(inputs=MyInput(question='q1')),
            Case(inputs=MyInput(question='q2')),
        ]
        result = client.add_cases('test-dataset', cases)
        assert result == [FAKE_CASE]

    def test_add_cases_with_tags(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests_seen.append(request)
            return httpx.Response(200, json=[FAKE_CASE])

        transport = httpx.MockTransport(handler)
        client = LogfireAPIClient(api_key='test-key', base_url='https://test.logfire.dev')
        client.client = httpx.Client(transport=transport, base_url='https://test.logfire.dev')

        cases: list[Case[MyInput, MyOutput, Any]] = [Case(inputs=MyInput(question='q1'))]
        client.add_cases('test-dataset', cases, tags=['bulk'])

        body = json.loads(requests_seen[0].content)
        assert body['cases'][0]['tags'] == ['bulk']

    def test_update_case_minimal(self):
        """When no params are set, sends empty body."""
        client = make_client()
        result = client.update_case('test-dataset', 'case-456')
        assert result == FAKE_CASE

    def test_update_case_full(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests_seen.append(request)
            return httpx.Response(200, json=FAKE_CASE)

        transport = httpx.MockTransport(handler)
        client = LogfireAPIClient(api_key='test-key', base_url='https://test.logfire.dev')
        client.client = httpx.Client(transport=transport, base_url='https://test.logfire.dev')

        @dataclass
        class MyEval:
            pass

        client.update_case(
            'test-dataset',
            'case-456',
            name='updated',
            inputs=MyInput(question='new'),
            expected_output=MyOutput(answer='new-answer'),
            metadata=MyMetadata(source='updated'),
            evaluators=[MyEval()],
            tags=['updated'],
        )

        body = json.loads(requests_seen[0].content)
        assert body['name'] == 'updated'
        assert body['inputs'] == {'question': 'new'}
        assert body['expected_output'] == {'answer': 'new-answer'}
        assert body['metadata'] == {'source': 'updated'}
        assert body['evaluators'] == [{'name': 'MyEval', 'arguments': None}]
        assert body['tags'] == ['updated']

    def test_update_case_clear_fields(self):
        """Pass None to explicitly clear nullable fields."""
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests_seen.append(request)
            return httpx.Response(200, json=FAKE_CASE)

        transport = httpx.MockTransport(handler)
        client = LogfireAPIClient(api_key='test-key', base_url='https://test.logfire.dev')
        client.client = httpx.Client(transport=transport, base_url='https://test.logfire.dev')

        client.update_case(
            'test-dataset',
            'case-456',
            name=None,
            expected_output=None,
            metadata=None,
            evaluators=None,
            tags=None,
        )

        body = json.loads(requests_seen[0].content)
        assert body['name'] is None
        assert body['expected_output'] is None
        assert body['metadata'] is None
        assert body['evaluators'] is None
        assert body['tags'] is None

    def test_update_case_dict_inputs(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests_seen.append(request)
            return httpx.Response(200, json=FAKE_CASE)

        transport = httpx.MockTransport(handler)
        client = LogfireAPIClient(api_key='test-key', base_url='https://test.logfire.dev')
        client.client = httpx.Client(transport=transport, base_url='https://test.logfire.dev')

        client.update_case(
            'test-dataset',
            'case-456',
            inputs={'question': 'dict-input'},
            expected_output={'answer': 'dict-output'},
            metadata={'source': 'dict-meta'},
        )

        body = json.loads(requests_seen[0].content)
        assert body['inputs'] == {'question': 'dict-input'}
        assert body['expected_output'] == {'answer': 'dict-output'}
        assert body['metadata'] == {'source': 'dict-meta'}

    def test_delete_case(self):
        client = make_client()
        result = client.delete_case('test-dataset', 'case-456')
        assert result is None

    def test_export_dataset_raw(self):
        """Without type args, returns raw dict."""
        client = make_client()
        result = client.export_dataset('test-dataset')
        assert result == FAKE_EXPORT

    def test_export_dataset_typed(self):
        """With type args, returns pydantic-evals Dataset."""
        client = make_client()
        result = client.export_dataset('test-dataset', input_type=MyInput, output_type=MyOutput)
        from pydantic_evals import Dataset

        assert isinstance(result, Dataset)

    def test_add_cases_with_dicts(self):
        client = make_client()
        cases: list[dict[str, Any]] = [{'inputs': {'question': 'q1'}}]
        result = client.add_cases('test-dataset', cases)
        assert result == [FAKE_CASE]

    def test_add_cases_dicts_with_tags(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests_seen.append(request)
            return httpx.Response(200, json=[FAKE_CASE])

        transport = httpx.MockTransport(handler)
        client = LogfireAPIClient(api_key='test-key', base_url='https://test.logfire.dev')
        client.client = httpx.Client(transport=transport, base_url='https://test.logfire.dev')

        cases: list[dict[str, Any]] = [{'inputs': {'question': 'q1'}}]
        client.add_cases('test-dataset', cases, tags=['imported'])

        body = json.loads(requests_seen[0].content)
        assert body['cases'][0]['tags'] == ['imported']

    def test_add_cases_dicts_not_mutated(self):
        """Ensure add_cases doesn't mutate caller's dicts when adding tags."""
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests_seen.append(request)
            return httpx.Response(200, json=[FAKE_CASE])

        transport = httpx.MockTransport(handler)
        client = LogfireAPIClient(api_key='test-key', base_url='https://test.logfire.dev')
        client.client = httpx.Client(transport=transport, base_url='https://test.logfire.dev')

        original_case: dict[str, Any] = {'inputs': {'question': 'q1'}}
        cases = [original_case]
        client.add_cases('test-dataset', cases, tags=['tagged'])

        # Original dict should NOT have been mutated
        assert 'tags' not in original_case

    def test_auth_header(self):
        """Client should set Authorization header."""
        client = LogfireAPIClient(api_key='my-secret-key', base_url='https://test.logfire.dev')
        assert client.client.headers['authorization'] == 'Bearer my-secret-key'
        client.client.close()


# =============================================================================
# Async client tests
# =============================================================================


class TestAsyncLogfireAPIClient:
    def test_init_with_base_url(self):
        client = AsyncLogfireAPIClient(api_key='test-key', base_url='https://custom.url')
        assert str(client.client.base_url) == 'https://custom.url'

    def test_init_with_client(self):
        httpx_client = httpx.AsyncClient(base_url='https://custom.url')
        client = AsyncLogfireAPIClient(client=httpx_client)
        assert client.client is httpx_client

    def test_init_requires_client_or_api_key(self):
        with pytest.raises(ValueError, match='Either client or api_key must be provided'):
            AsyncLogfireAPIClient()

    @pytest.mark.anyio
    async def test_context_manager(self):
        client = make_async_client()
        async with client as c:
            assert c is client

    @pytest.mark.anyio
    async def test_list_datasets(self):
        client = make_async_client()
        result = await client.list_datasets()
        assert result == [FAKE_DATASET]

    @pytest.mark.anyio
    async def test_get_dataset(self):
        client = make_async_client()
        result = await client.get_dataset('test-dataset')
        assert result == FAKE_DATASET

    @pytest.mark.anyio
    async def test_create_dataset_minimal(self):
        client = make_async_client()
        result = await client.create_dataset(name='test-dataset')
        assert result == FAKE_DATASET

    @pytest.mark.anyio
    async def test_create_dataset_full(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests_seen.append(request)
            return httpx.Response(200, json=FAKE_DATASET)

        transport = httpx.MockTransport(handler)
        client = AsyncLogfireAPIClient(api_key='test-key', base_url='https://test.logfire.dev')
        client.client = httpx.AsyncClient(transport=transport, base_url='https://test.logfire.dev')

        await client.create_dataset(
            name='test-dataset',
            input_type=MyInput,
            output_type=MyOutput,
            metadata_type=MyMetadata,
            description='A test dataset',
            guidance='Be helpful',
            ai_managed_guidance=True,
        )

        body = json.loads(requests_seen[0].content)
        assert body['name'] == 'test-dataset'
        assert 'input_schema' in body
        assert 'output_schema' in body
        assert 'metadata_schema' in body
        assert body['description'] == 'A test dataset'
        assert body['guidance'] == 'Be helpful'
        assert body['ai_managed_guidance'] is True

    @pytest.mark.anyio
    async def test_update_dataset_minimal(self):
        client = make_async_client()
        result = await client.update_dataset('test-dataset')
        assert result == FAKE_DATASET

    @pytest.mark.anyio
    async def test_update_dataset_full(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests_seen.append(request)
            return httpx.Response(200, json=FAKE_DATASET)

        transport = httpx.MockTransport(handler)
        client = AsyncLogfireAPIClient(api_key='test-key', base_url='https://test.logfire.dev')
        client.client = httpx.AsyncClient(transport=transport, base_url='https://test.logfire.dev')

        await client.update_dataset(
            'test-dataset',
            name='new-name',
            input_type=MyInput,
            output_type=MyOutput,
            metadata_type=MyMetadata,
            description='Updated desc',
            guidance='New guidance',
            ai_managed_guidance=True,
        )

        body = json.loads(requests_seen[0].content)
        assert body['name'] == 'new-name'
        assert body['description'] == 'Updated desc'
        assert 'input_schema' in body
        assert body['guidance'] == 'New guidance'
        assert body['ai_managed_guidance'] is True

    @pytest.mark.anyio
    async def test_update_dataset_clear_fields(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests_seen.append(request)
            return httpx.Response(200, json=FAKE_DATASET)

        transport = httpx.MockTransport(handler)
        client = AsyncLogfireAPIClient(api_key='test-key', base_url='https://test.logfire.dev')
        client.client = httpx.AsyncClient(transport=transport, base_url='https://test.logfire.dev')

        await client.update_dataset('test-dataset', description=None, guidance=None)

        body = json.loads(requests_seen[0].content)
        assert body['description'] is None
        assert body['guidance'] is None

    @pytest.mark.anyio
    async def test_delete_dataset(self):
        client = make_async_client()
        result = await client.delete_dataset('test-dataset')
        assert result is None

    @pytest.mark.anyio
    async def test_list_cases(self):
        client = make_async_client()
        result = await client.list_cases('test-dataset')
        assert result == [FAKE_CASE]

    @pytest.mark.anyio
    async def test_list_cases_with_tags(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests_seen.append(request)
            return httpx.Response(200, json=[FAKE_CASE])

        transport = httpx.MockTransport(handler)
        client = AsyncLogfireAPIClient(api_key='test-key', base_url='https://test.logfire.dev')
        client.client = httpx.AsyncClient(transport=transport, base_url='https://test.logfire.dev')

        await client.list_cases('test-dataset', tags=['tag1'])
        assert 'tags' in str(requests_seen[0].url)

    @pytest.mark.anyio
    async def test_get_case(self):
        client = make_async_client()
        result = await client.get_case('test-dataset', 'case-456')
        assert result == FAKE_CASE

    @pytest.mark.anyio
    async def test_add_cases(self):
        client = make_async_client()
        cases: list[Case[MyInput, MyOutput, Any]] = [Case(inputs=MyInput(question='q1'))]
        result = await client.add_cases('test-dataset', cases)
        assert result == [FAKE_CASE]

    @pytest.mark.anyio
    async def test_add_cases_with_tags(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests_seen.append(request)
            return httpx.Response(200, json=[FAKE_CASE])

        transport = httpx.MockTransport(handler)
        client = AsyncLogfireAPIClient(api_key='test-key', base_url='https://test.logfire.dev')
        client.client = httpx.AsyncClient(transport=transport, base_url='https://test.logfire.dev')

        cases: list[Case[MyInput, MyOutput, Any]] = [Case(inputs=MyInput(question='q1'))]
        await client.add_cases('test-dataset', cases, tags=['bulk'])

        body = json.loads(requests_seen[0].content)
        assert body['cases'][0]['tags'] == ['bulk']

    @pytest.mark.anyio
    async def test_update_case_minimal(self):
        client = make_async_client()
        result = await client.update_case('test-dataset', 'case-456')
        assert result == FAKE_CASE

    @pytest.mark.anyio
    async def test_update_case_full(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests_seen.append(request)
            return httpx.Response(200, json=FAKE_CASE)

        transport = httpx.MockTransport(handler)
        client = AsyncLogfireAPIClient(api_key='test-key', base_url='https://test.logfire.dev')
        client.client = httpx.AsyncClient(transport=transport, base_url='https://test.logfire.dev')

        @dataclass
        class MyEval:
            pass

        await client.update_case(
            'test-dataset',
            'case-456',
            name='updated',
            inputs=MyInput(question='new'),
            expected_output=MyOutput(answer='new-answer'),
            metadata=MyMetadata(source='updated'),
            evaluators=[MyEval()],
            tags=['updated'],
        )

        body = json.loads(requests_seen[0].content)
        assert body['name'] == 'updated'
        assert body['inputs'] == {'question': 'new'}
        assert body['expected_output'] == {'answer': 'new-answer'}
        assert body['metadata'] == {'source': 'updated'}
        assert body['tags'] == ['updated']

    @pytest.mark.anyio
    async def test_update_case_clear_fields(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests_seen.append(request)
            return httpx.Response(200, json=FAKE_CASE)

        transport = httpx.MockTransport(handler)
        client = AsyncLogfireAPIClient(api_key='test-key', base_url='https://test.logfire.dev')
        client.client = httpx.AsyncClient(transport=transport, base_url='https://test.logfire.dev')

        await client.update_case(
            'test-dataset',
            'case-456',
            name=None,
            expected_output=None,
            metadata=None,
            evaluators=None,
            tags=None,
        )

        body = json.loads(requests_seen[0].content)
        assert body['name'] is None
        assert body['expected_output'] is None
        assert body['metadata'] is None
        assert body['evaluators'] is None
        assert body['tags'] is None

    @pytest.mark.anyio
    async def test_update_case_dict_inputs(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests_seen.append(request)
            return httpx.Response(200, json=FAKE_CASE)

        transport = httpx.MockTransport(handler)
        client = AsyncLogfireAPIClient(api_key='test-key', base_url='https://test.logfire.dev')
        client.client = httpx.AsyncClient(transport=transport, base_url='https://test.logfire.dev')

        await client.update_case(
            'test-dataset',
            'case-456',
            inputs={'question': 'dict-input'},
            expected_output={'answer': 'dict-output'},
            metadata={'source': 'dict-meta'},
        )

        body = json.loads(requests_seen[0].content)
        assert body['inputs'] == {'question': 'dict-input'}
        assert body['expected_output'] == {'answer': 'dict-output'}
        assert body['metadata'] == {'source': 'dict-meta'}

    @pytest.mark.anyio
    async def test_delete_case(self):
        client = make_async_client()
        result = await client.delete_case('test-dataset', 'case-456')
        assert result is None

    @pytest.mark.anyio
    async def test_export_dataset_raw(self):
        client = make_async_client()
        result = await client.export_dataset('test-dataset')
        assert result == FAKE_EXPORT

    @pytest.mark.anyio
    async def test_export_dataset_typed(self):
        client = make_async_client()
        result = await client.export_dataset('test-dataset', input_type=MyInput, output_type=MyOutput)
        from pydantic_evals import Dataset

        assert isinstance(result, Dataset)

    @pytest.mark.anyio
    async def test_add_cases_with_dicts(self):
        client = make_async_client()
        cases: list[dict[str, Any]] = [{'inputs': {'question': 'q1'}}]
        result = await client.add_cases('test-dataset', cases)
        assert result == [FAKE_CASE]

    @pytest.mark.anyio
    async def test_add_cases_dicts_with_tags(self):
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests_seen.append(request)
            return httpx.Response(200, json=[FAKE_CASE])

        transport = httpx.MockTransport(handler)
        client = AsyncLogfireAPIClient(api_key='test-key', base_url='https://test.logfire.dev')
        client.client = httpx.AsyncClient(transport=transport, base_url='https://test.logfire.dev')

        cases: list[dict[str, Any]] = [{'inputs': {'question': 'q1'}}]
        await client.add_cases('test-dataset', cases, tags=['imported'])

        body = json.loads(requests_seen[0].content)
        assert body['cases'][0]['tags'] == ['imported']

    @pytest.mark.anyio
    async def test_add_cases_dicts_not_mutated(self):
        """Ensure async add_cases doesn't mutate caller's dicts."""
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests_seen.append(request)
            return httpx.Response(200, json=[FAKE_CASE])

        transport = httpx.MockTransport(handler)
        client = AsyncLogfireAPIClient(api_key='test-key', base_url='https://test.logfire.dev')
        client.client = httpx.AsyncClient(transport=transport, base_url='https://test.logfire.dev')

        original_case: dict[str, Any] = {'inputs': {'question': 'q1'}}
        cases = [original_case]
        await client.add_cases('test-dataset', cases, tags=['tagged'])

        assert 'tags' not in original_case
