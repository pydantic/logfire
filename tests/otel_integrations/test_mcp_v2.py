"""Tests for `logfire.instrument_mcp()` with mcp 2, which fastmcp 4 depends on.

mcp 2 emits OpenTelemetry spans and propagates trace context by itself, so `instrument_mcp()`
only warns that it's unnecessary. These tests run in CI in a separate step that installs
`fastmcp>=4` on top of the locked environment (see `.github/workflows/main.yml`).
"""

import pytest
from inline_snapshot import snapshot

import logfire
from logfire.testing import TestExporter

pytest.importorskip('fastmcp', minversion='4')

from fastmcp import Client, FastMCP

UNNECESSARY = r'`logfire\.instrument_mcp\(\)` is unnecessary with mcp 2'


@pytest.mark.anyio
async def test_instrument_mcp_v2_builtin_otel(exporter: TestExporter):
    with pytest.warns(UserWarning, match=UNNECESSARY):
        logfire.instrument_mcp()

    server = FastMCP('demo')

    def add(a: int, b: int) -> int:
        with logfire.span('inside tool'):
            return a + b

    server.tool(add)

    with logfire.span('client'):
        async with Client(server) as client:
            result = await client.call_tool('add', {'a': 1, 'b': 2})

    assert result.data == 3
    assert exporter.exported_spans_as_dict(parse_json_attributes=True) == snapshot(
        [
            {
                'name': 'server/discover',
                'context': {'trace_id': 1, 'span_id': 5, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
                'start_time': 3000000000,
                'end_time': 4000000000,
                'attributes': {
                    'fastmcp.span.seam': True,
                    'mcp.method.name': 'server/discover',
                    'fastmcp.server.name': 'demo',
                    'mcp.protocol.version': '2026-07-28',
                    'logfire.span_type': 'span',
                    'logfire.msg': 'server/discover',
                },
            },
            {
                'name': 'MCP send server/discover',
                'context': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 2000000000,
                'end_time': 5000000000,
                'attributes': {
                    'mcp.method.name': 'server/discover',
                    'jsonrpc.request.id': '1',
                    'logfire.span_type': 'span',
                    'logfire.msg': 'MCP send server/discover',
                },
            },
            {
                'name': 'inside tool',
                'context': {'trace_id': 1, 'span_id': 13, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 11, 'is_remote': False},
                'start_time': 9000000000,
                'end_time': 10000000000,
                'attributes': {
                    'code.filepath': 'test_mcp_v2.py',
                    'code.function': 'add',
                    'code.lineno': 123,
                    'logfire.msg_template': 'inside tool',
                    'logfire.msg': 'inside tool',
                    'logfire.span_type': 'span',
                },
            },
            {
                'name': 'tools/call add',
                'context': {'trace_id': 1, 'span_id': 11, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 9, 'is_remote': False},
                'start_time': 8000000000,
                'end_time': 11000000000,
                'attributes': {
                    'fastmcp.span.seam': True,
                    'logfire.span_type': 'span',
                    'logfire.msg': 'tools/call',
                    'mcp.method.name': 'tools/call',
                    'fastmcp.server.name': 'demo',
                    'mcp.protocol.version': '2026-07-28',
                    'mcp.session.id': "[Scrubbed due to 'session']",
                    'gen_ai.tool.name': 'add',
                    'fastmcp.component.key': 'tool:add@',
                    'fastmcp.component.type': 'tool',
                    'fastmcp.provider.type': 'LocalProvider',
                    'logfire.scrubbed': [{'path': ['attributes', 'mcp.session.id'], 'matched_substring': 'session'}],
                },
            },
            {
                'name': 'MCP send tools/call add',
                'context': {'trace_id': 1, 'span_id': 9, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 7, 'is_remote': False},
                'start_time': 7000000000,
                'end_time': 12000000000,
                'attributes': {
                    'mcp.method.name': 'tools/call',
                    'jsonrpc.request.id': '2',
                    'logfire.span_type': 'span',
                    'logfire.msg': 'MCP send tools/call add',
                },
            },
            {
                'name': 'tools/list',
                'context': {'trace_id': 1, 'span_id': 17, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 15, 'is_remote': False},
                'start_time': 14000000000,
                'end_time': 15000000000,
                'attributes': {
                    'fastmcp.span.seam': True,
                    'logfire.span_type': 'span',
                    'logfire.msg': 'tools/list',
                    'mcp.method.name': 'tools/list',
                    'fastmcp.server.name': 'demo',
                    'fastmcp.component.type': 'tool',
                    'fastmcp.component.key': '',
                    'mcp.protocol.version': '2026-07-28',
                    'mcp.session.id': "[Scrubbed due to 'session']",
                    'logfire.scrubbed': [{'path': ['attributes', 'mcp.session.id'], 'matched_substring': 'session'}],
                },
            },
            {
                'name': 'MCP send tools/list',
                'context': {'trace_id': 1, 'span_id': 15, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 7, 'is_remote': False},
                'start_time': 13000000000,
                'end_time': 16000000000,
                'attributes': {
                    'mcp.method.name': 'tools/list',
                    'jsonrpc.request.id': '3',
                    'logfire.span_type': 'span',
                    'logfire.msg': 'MCP send tools/list',
                },
            },
            {
                'name': 'tools/call add',
                'context': {'trace_id': 1, 'span_id': 7, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 6000000000,
                'end_time': 17000000000,
                'attributes': {
                    'mcp.method.name': 'tools/call',
                    'fastmcp.component.key': 'add',
                    'gen_ai.tool.name': 'add',
                    'logfire.span_type': 'span',
                    'logfire.msg': 'tools/call add',
                },
            },
            {
                'name': 'client',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 18000000000,
                'attributes': {
                    'code.filepath': 'test_mcp_v2.py',
                    'code.function': 'test_instrument_mcp_v2_builtin_otel',
                    'code.lineno': 123,
                    'logfire.msg_template': 'client',
                    'logfire.msg': 'client',
                    'logfire.span_type': 'span',
                },
            },
        ]
    )


def test_instrument_mcp_v2_propagate_otel_context_false():
    with pytest.warns(UserWarning, match=r'`propagate_otel_context=False` is ignored'):
        logfire.instrument_mcp(propagate_otel_context=False)
