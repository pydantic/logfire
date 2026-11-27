"""Regression tests for errors raised by non-streaming LLM requests."""

from __future__ import annotations

import anthropic
import httpx2
import openai
import pydantic
import pytest
from inline_snapshot import snapshot

import logfire
from logfire._internal.utils import get_version
from logfire.testing import TestExporter

requires_anthropic_pydantic = pytest.mark.skipif(
    get_version(pydantic.__version__) < get_version('2.5'),
    reason='Requires Pydantic 2.5 or higher to import genai-prices and set operation.cost attribute.',
)


def openai_error_handler(request: httpx2.Request) -> httpx2.Response:
    assert request.url == 'https://example.invalid/v1/chat/completions'
    return httpx2.Response(500, json={'error': {'message': 'boom', 'type': 'server_error'}})


def anthropic_error_handler(request: httpx2.Request) -> httpx2.Response:
    assert request.url == 'https://example.invalid/v1/messages'
    return httpx2.Response(429, json={'type': 'error', 'error': {'type': 'rate_limit_error', 'message': 'slow down'}})


def test_openai_request_failure_records_error_type(exporter: TestExporter) -> None:
    with httpx2.Client(transport=httpx2.MockTransport(openai_error_handler)) as httpx_client:
        client = openai.Client(
            api_key='unused', base_url='https://example.invalid/v1', http_client=httpx_client, max_retries=0
        )
        with logfire.instrument_openai(client):
            with pytest.raises(openai.InternalServerError, match='boom'):
                client.chat.completions.create(model='test-model', messages=[{'role': 'user', 'content': 'hello'}])

    assert exporter.exported_spans_as_dict(parse_json_attributes=True) == snapshot(
        [
            {
                'name': 'Chat Completion with {request_data[model]!r}',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 3000000000,
                'attributes': {
                    'code.filepath': 'test_llm_request_errors.py',
                    'code.function': 'test_openai_request_failure_records_error_type',
                    'code.lineno': 123,
                    'request_data': {'model': 'test-model'},
                    'gen_ai.system': 'openai',
                    'gen_ai.provider.name': 'openai',
                    'gen_ai.request.model': 'test-model',
                    'gen_ai.operation.name': 'chat',
                    'gen_ai.input.messages': ({'role': 'user', 'parts': ({'type': 'text', 'content': 'hello'},)},),
                    'async': False,
                    'logfire.msg_template': 'Chat Completion with {request_data[model]!r}',
                    'logfire.msg': "Chat Completion with 'test-model'",
                    'logfire.json_schema': {
                        'type': 'object',
                        'properties': {
                            'request_data': {},
                            'gen_ai.system': {},
                            'gen_ai.provider.name': {},
                            'gen_ai.request.model': {},
                            'gen_ai.operation.name': {},
                            'gen_ai.input.messages': {},
                            'async': {},
                            'error.type': {},
                        },
                    },
                    'logfire.tags': ('LLM',),
                    'error.type': 'InternalServerError',
                    'logfire.span_type': 'span',
                    'logfire.level_num': 17,
                    'logfire.exception.fingerprint': '0000000000000000000000000000000000000000000000000000000000000000',
                    'gen_ai.response.model': 'test-model',
                },
                'events': [
                    {
                        'name': 'exception',
                        'timestamp': 2000000000,
                        'attributes': {
                            'exception.type': 'openai.InternalServerError',
                            'exception.message': 'Error code: 500 - boom',
                            'exception.stacktrace': 'openai.InternalServerError: Error code: 500 - boom',
                            'exception.escaped': 'True',
                        },
                    }
                ],
            }
        ]
    )


@pytest.mark.anyio
async def test_openai_async_request_failure_records_error_type(exporter: TestExporter) -> None:
    async with httpx2.AsyncClient(transport=httpx2.MockTransport(openai_error_handler)) as httpx_client:
        client = openai.AsyncClient(
            api_key='unused', base_url='https://example.invalid/v1', http_client=httpx_client, max_retries=0
        )
        with logfire.instrument_openai(client):
            with pytest.raises(openai.InternalServerError, match='boom'):
                await client.chat.completions.create(
                    model='test-model', messages=[{'role': 'user', 'content': 'hello'}]
                )

    assert exporter.exported_spans_as_dict(parse_json_attributes=True) == snapshot(
        [
            {
                'name': 'Chat Completion with {request_data[model]!r}',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 3000000000,
                'attributes': {
                    'code.filepath': 'test_llm_request_errors.py',
                    'code.function': 'test_openai_async_request_failure_records_error_type',
                    'code.lineno': 123,
                    'request_data': {'model': 'test-model'},
                    'gen_ai.system': 'openai',
                    'gen_ai.provider.name': 'openai',
                    'gen_ai.request.model': 'test-model',
                    'gen_ai.operation.name': 'chat',
                    'gen_ai.input.messages': ({'role': 'user', 'parts': ({'type': 'text', 'content': 'hello'},)},),
                    'async': True,
                    'logfire.msg_template': 'Chat Completion with {request_data[model]!r}',
                    'logfire.msg': "Chat Completion with 'test-model'",
                    'logfire.json_schema': {
                        'type': 'object',
                        'properties': {
                            'request_data': {},
                            'gen_ai.system': {},
                            'gen_ai.provider.name': {},
                            'gen_ai.request.model': {},
                            'gen_ai.operation.name': {},
                            'gen_ai.input.messages': {},
                            'async': {},
                            'error.type': {},
                        },
                    },
                    'logfire.tags': ('LLM',),
                    'error.type': 'InternalServerError',
                    'logfire.span_type': 'span',
                    'logfire.level_num': 17,
                    'logfire.exception.fingerprint': '0000000000000000000000000000000000000000000000000000000000000000',
                    'gen_ai.response.model': 'test-model',
                },
                'events': [
                    {
                        'name': 'exception',
                        'timestamp': 2000000000,
                        'attributes': {
                            'exception.type': 'openai.InternalServerError',
                            'exception.message': 'Error code: 500 - boom',
                            'exception.stacktrace': 'openai.InternalServerError: Error code: 500 - boom',
                            'exception.escaped': 'True',
                        },
                    }
                ],
            }
        ]
    )


@requires_anthropic_pydantic
def test_anthropic_request_failure_records_error_type(exporter: TestExporter) -> None:
    with httpx2.Client(transport=httpx2.MockTransport(anthropic_error_handler)) as httpx_client:
        client = anthropic.Anthropic(
            api_key='unused', base_url='https://example.invalid', http_client=httpx_client, max_retries=0
        )
        with logfire.instrument_anthropic(client):
            with pytest.raises(anthropic.RateLimitError, match='slow down'):
                client.messages.create(
                    max_tokens=10, model='test-model', messages=[{'role': 'user', 'content': 'hello'}]
                )

    assert exporter.exported_spans_as_dict(parse_json_attributes=True) == snapshot(
        [
            {
                'name': 'anthropic.messages.create',
                'context': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 2000000000,
                'end_time': 3000000000,
                'attributes': {
                    'server.address': 'example.invalid',
                    'server.port': 443,
                    'gen_ai.provider.name': 'anthropic',
                    'gen_ai.operation.name': 'chat',
                    'gen_ai.request.model': 'test-model',
                    'gen_ai.request.max_tokens': 10,
                    'http.request.method': 'POST',
                    'http.route': '/v1/messages',
                    'logfire.span_type': 'span',
                    'logfire.msg': 'anthropic.messages.create',
                    'url.scheme': 'https',
                    'url.path': '/v1/messages',
                    'url.full': 'https://example.invalid/v1/messages',
                    'http.response.status_code': 429,
                    'error.type': 'rate_limit_error',
                    'logfire.level_num': 17,
                    'gen_ai.response.model': 'test-model',
                },
            },
            {
                'name': 'Message with {request_data[model]!r}',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 5000000000,
                'attributes': {
                    'code.filepath': 'test_llm_request_errors.py',
                    'code.function': 'test_anthropic_request_failure_records_error_type',
                    'code.lineno': 123,
                    'request_data': {'model': 'test-model'},
                    'gen_ai.system': 'anthropic',
                    'gen_ai.provider.name': 'anthropic',
                    'gen_ai.request.model': 'test-model',
                    'gen_ai.operation.name': 'chat',
                    'gen_ai.request.max_tokens': 10,
                    'gen_ai.input.messages': ({'role': 'user', 'parts': ({'type': 'text', 'content': 'hello'},)},),
                    'async': False,
                    'logfire.msg_template': 'Message with {request_data[model]!r}',
                    'logfire.msg': "Message with 'test-model'",
                    'logfire.json_schema': {
                        'type': 'object',
                        'properties': {
                            'request_data': {},
                            'gen_ai.system': {},
                            'gen_ai.provider.name': {},
                            'gen_ai.request.model': {},
                            'gen_ai.operation.name': {},
                            'gen_ai.request.max_tokens': {},
                            'gen_ai.input.messages': {},
                            'async': {},
                            'error.type': {},
                        },
                    },
                    'logfire.tags': ('LLM',),
                    'error.type': 'RateLimitError',
                    'logfire.span_type': 'span',
                    'logfire.level_num': 17,
                    'logfire.exception.fingerprint': '0000000000000000000000000000000000000000000000000000000000000000',
                    'gen_ai.response.model': 'test-model',
                },
                'events': [
                    {
                        'name': 'exception',
                        'timestamp': 4000000000,
                        'attributes': {
                            'exception.type': 'anthropic.RateLimitError',
                            'exception.message': "Error code: 429 - {'type': 'error', 'error': {'type': 'rate_limit_error', 'message': 'slow down'}}",
                            'exception.stacktrace': "anthropic.RateLimitError: Error code: 429 - {'type': 'error', 'error': {'type': 'rate_limit_error', 'message': 'slow down'}}",
                            'exception.escaped': 'True',
                        },
                    }
                ],
            },
        ]
    )


@requires_anthropic_pydantic
@pytest.mark.anyio
async def test_anthropic_async_request_failure_records_error_type(exporter: TestExporter) -> None:
    async with httpx2.AsyncClient(transport=httpx2.MockTransport(anthropic_error_handler)) as httpx_client:
        client = anthropic.AsyncAnthropic(
            api_key='unused', base_url='https://example.invalid', http_client=httpx_client, max_retries=0
        )
        with logfire.instrument_anthropic(client):
            with pytest.raises(anthropic.RateLimitError, match='slow down'):
                await client.messages.create(
                    max_tokens=10, model='test-model', messages=[{'role': 'user', 'content': 'hello'}]
                )

    assert exporter.exported_spans_as_dict(parse_json_attributes=True) == snapshot(
        [
            {
                'name': 'anthropic.messages.create',
                'context': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 2000000000,
                'end_time': 3000000000,
                'attributes': {
                    'server.address': 'example.invalid',
                    'server.port': 443,
                    'gen_ai.provider.name': 'anthropic',
                    'gen_ai.operation.name': 'chat',
                    'gen_ai.request.model': 'test-model',
                    'gen_ai.request.max_tokens': 10,
                    'http.request.method': 'POST',
                    'http.route': '/v1/messages',
                    'logfire.span_type': 'span',
                    'logfire.msg': 'anthropic.messages.create',
                    'url.scheme': 'https',
                    'url.path': '/v1/messages',
                    'url.full': 'https://example.invalid/v1/messages',
                    'http.response.status_code': 429,
                    'error.type': 'rate_limit_error',
                    'logfire.level_num': 17,
                    'gen_ai.response.model': 'test-model',
                },
            },
            {
                'name': 'Message with {request_data[model]!r}',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 5000000000,
                'attributes': {
                    'code.filepath': 'test_llm_request_errors.py',
                    'code.function': 'test_anthropic_async_request_failure_records_error_type',
                    'code.lineno': 123,
                    'request_data': {'model': 'test-model'},
                    'gen_ai.system': 'anthropic',
                    'gen_ai.provider.name': 'anthropic',
                    'gen_ai.request.model': 'test-model',
                    'gen_ai.operation.name': 'chat',
                    'gen_ai.request.max_tokens': 10,
                    'gen_ai.input.messages': ({'role': 'user', 'parts': ({'type': 'text', 'content': 'hello'},)},),
                    'async': True,
                    'logfire.msg_template': 'Message with {request_data[model]!r}',
                    'logfire.msg': "Message with 'test-model'",
                    'logfire.json_schema': {
                        'type': 'object',
                        'properties': {
                            'request_data': {},
                            'gen_ai.system': {},
                            'gen_ai.provider.name': {},
                            'gen_ai.request.model': {},
                            'gen_ai.operation.name': {},
                            'gen_ai.request.max_tokens': {},
                            'gen_ai.input.messages': {},
                            'async': {},
                            'error.type': {},
                        },
                    },
                    'logfire.tags': ('LLM',),
                    'error.type': 'RateLimitError',
                    'logfire.span_type': 'span',
                    'logfire.level_num': 17,
                    'logfire.exception.fingerprint': '0000000000000000000000000000000000000000000000000000000000000000',
                    'gen_ai.response.model': 'test-model',
                },
                'events': [
                    {
                        'name': 'exception',
                        'timestamp': 4000000000,
                        'attributes': {
                            'exception.type': 'anthropic.RateLimitError',
                            'exception.message': "Error code: 429 - {'type': 'error', 'error': {'type': 'rate_limit_error', 'message': 'slow down'}}",
                            'exception.stacktrace': "anthropic.RateLimitError: Error code: 429 - {'type': 'error', 'error': {'type': 'rate_limit_error', 'message': 'slow down'}}",
                            'exception.escaped': 'True',
                        },
                    }
                ],
            },
        ]
    )
