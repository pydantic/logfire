from __future__ import annotations

import pytest

pytest.importorskip('pydantic', minversion='2.12')

from fastmcp import FastMCP
from pydantic_ai import Agent
from pydantic_ai.mcp import MCPToolset
from pydantic_ai.messages import ModelMessage, ModelRequest, ModelResponse, ToolCallPart, ToolReturnPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

import logfire
from examples.python.public_search_citations import Answer, answer_question, citation_counts
from logfire.testing import TestExporter

SOURCE = 'https://docs.python.org/3/library/asyncio-task.html'
UNRETURNED = 'https://docs.python.org/3/library/asyncio.html'


def test_citation_counts():
    answer = Answer(answer='An answer.', citations=[SOURCE, SOURCE, UNRETURNED])
    messages = [
        ModelRequest(
            parts=[
                ToolReturnPart(
                    'web_search',
                    {'results': [{'url': SOURCE}, {'url': SOURCE}], 'note': UNRETURNED},
                ),
                ToolReturnPart('another_tool', {'results': [{'url': UNRETURNED}]}),
                ToolReturnPart('web_search', {'results': [{'url': UNRETURNED}]}, outcome='failed'),
                ToolReturnPart('web_search', {'results': [{'url': UNRETURNED}]}, outcome='denied'),
            ]
        ),
    ]
    assert citation_counts(answer, messages) == {
        'retrieved_url_count': 1,
        'citation_count': 2,
        'matched_citation_count': 1,
        'unmatched_citation_count': 1,
    }
    assert citation_counts(Answer(answer='No evidence.', citations=[]), []) == {
        'retrieved_url_count': 0,
        'citation_count': 0,
        'matched_citation_count': 0,
        'unmatched_citation_count': 0,
    }


@pytest.mark.anyio
async def test_search_agent_counts_on_trace(exporter: TestExporter):
    server = FastMCP()
    calls: list[str] = []

    @server.tool
    def web_search(objective: str) -> dict[str, object]:
        """Find public documentation."""
        calls.append(objective)
        return {'results': [{'url': SOURCE, 'excerpts': ['All tasks are awaited when the context manager exits.']}]}

    def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        if len(messages) == 1:
            return ModelResponse(parts=[ToolCallPart('web_search', {'objective': 'Python TaskGroup documentation'})])
        assert info.output_tools
        return ModelResponse(
            parts=[
                ToolCallPart(
                    info.output_tools[0].name,
                    {'answer': 'All tasks are awaited on exit.', 'citations': [SOURCE, SOURCE, UNRETURNED]},
                )
            ]
        )

    logfire.instrument_pydantic_ai()
    try:
        answer, counts = await answer_question(
            'When are TaskGroup tasks awaited?', FunctionModel(respond), MCPToolset(server)
        )
    finally:
        Agent.instrument_all(False)
    assert calls == ['Python TaskGroup documentation']
    assert answer.citations == [SOURCE, SOURCE, UNRETURNED]
    assert counts == {
        'retrieved_url_count': 1,
        'citation_count': 2,
        'matched_citation_count': 1,
        'unmatched_citation_count': 1,
    }
    spans = exporter.exported_spans_as_dict(parse_json_attributes=True)
    parent = next(span for span in spans if span['name'] == 'public web search')
    assert all(parent['attributes'][key] == value for key, value in counts.items())
    assert any(span['parent'] == parent['context'] and span['name'] != 'public web search' for span in spans)


@pytest.mark.anyio
async def test_provider_error_has_no_citation_counts(exporter: TestExporter):
    server = FastMCP()

    def fail(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        raise RuntimeError('Provider unavailable')

    with pytest.raises(RuntimeError, match='Provider unavailable'):
        await answer_question('Public documentation question', FunctionModel(fail), MCPToolset(server))
    spans = exporter.exported_spans_as_dict(parse_json_attributes=True)
    parent = next(span for span in spans if span['name'] == 'public web search')
    assert 'citation_count' not in parent['attributes']
