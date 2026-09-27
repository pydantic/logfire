"""Regression tests for errors raised during OpenAI stream consumption."""

import json
from collections.abc import Iterator

import httpx
import openai
import pytest
from httpx._transports.mock import MockTransport

import logfire
from logfire.testing import TestExporter


class FailingChatStream(httpx.SyncByteStream):
    def __init__(self, *, chunks_before_error: int) -> None:
        self.chunks_before_error = chunks_before_error

    def __iter__(self) -> Iterator[bytes]:
        for index in range(self.chunks_before_error):
            chunk = {
                'id': 'chatcmpl-local',
                'object': 'chat.completion.chunk',
                'created': 0,
                'model': 'test-model',
                'choices': [{'index': 0, 'delta': {'content': str(index)}, 'finish_reason': None}],
            }
            yield ('data: ' + json.dumps(chunk) + '\n\n').encode()
        yield b'data: {"error":{"message":"stream failed","type":"server_error"}}\n\n'


@pytest.mark.parametrize('chunks_before_error', [0, 2])
def test_chat_completions_stream_failure_records_model_error(exporter: TestExporter, chunks_before_error: int) -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        assert request.url == 'https://example.invalid/v1/chat/completions'
        return httpx.Response(
            200,
            headers={'content-type': 'text/event-stream'},
            stream=FailingChatStream(chunks_before_error=chunks_before_error),
        )

    with httpx.Client(transport=MockTransport(handle)) as httpx_client:
        client = openai.Client(
            api_key='unused', base_url='https://example.invalid/v1', http_client=httpx_client, max_retries=0
        )
        with logfire.instrument_openai(client):
            response = client.chat.completions.create(
                model='test-model', messages=[{'role': 'user', 'content': 'hello'}], stream=True
            )
            with pytest.raises(openai.APIError, match='stream failed'):
                list(response)

    spans = exporter.exported_spans_as_dict()
    model_log = next(span for span in spans if 'streaming response' in span['name'])
    assert model_log['attributes']['error.type'] == 'APIError'
    assert model_log['attributes']['logfire.level_num'] == 17
    assert [event['name'] for event in model_log['events']] == ['exception']
