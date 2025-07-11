# No from __future__ import annotations here
# because it breaks `ctx: Context` being recognised by `@fastmcp.tool()` properly.

import asyncio
import os
import sys
import warnings
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any

import pydantic
import pytest
from dirty_equals import IsStr

import logfire
from logfire._internal.exporters.test import TestExporter
from logfire._internal.utils import get_version
from tests.otel_integrations.test_openai_agents import simplify_spans

try:
    from agents import Agent, Runner, trace
    from agents.mcp.server import _MCPServerWithClientSession  # type: ignore
    from inline_snapshot import snapshot
    from mcp.server.fastmcp import Context, FastMCP
    from mcp.shared.memory import create_client_server_memory_streams
except ImportError:
    pytestmark = [
        pytest.mark.skipif(sys.version_info < (3, 10), reason='Requires Python 3.10 or higher'),
        pytest.mark.skipif(
            get_version(pydantic.__version__) < get_version('2.7'), reason='Requires Pydantic 2.7 or higher'
        ),
    ]
    if TYPE_CHECKING:
        assert False


os.environ.setdefault('OPENAI_API_KEY', 'foo')


@pytest.mark.vcr()
@pytest.mark.anyio
async def test_mcp(exporter: TestExporter):
    logfire.instrument_openai_agents()
    logfire.instrument_mcp()

    fastmcp = FastMCP()

    @fastmcp.tool()
    async def random_number(ctx: Context) -> int:  # type: ignore
        await ctx.info('Generating a random number')
        await ctx.log(
            'alert',  # type: ignore  # mcp type hints problem
            'Dice broken! Improvising...',
            logger_name='my_logger',
        )
        return 4

    async with create_client_server_memory_streams() as (client_streams, server_streams):
        lowlevel_mcp = fastmcp._mcp_server  # type: ignore
        asyncio.create_task(
            lowlevel_mcp.run(
                *server_streams,
                lowlevel_mcp.create_initialization_options(),
                raise_exceptions=True,
            )
        )

        class MyMCPServer(_MCPServerWithClientSession):
            def __init__(self, streams: Any):
                super().__init__(cache_tools_list=False, client_session_timeout_seconds=1000)
                self._streams = streams

            @asynccontextmanager
            async def create_streams(self):
                yield self._streams

            @property
            def name(self):
                return 'MyMCPServer'

        async with MyMCPServer(client_streams) as openai_mcp_server:
            agent = Agent(name='Assistant', mcp_servers=[openai_mcp_server])
            with warnings.catch_warnings(), trace('my_trace', trace_id='trace_123'):
                # OpenAI accesses model_fields on an instance which is deprecated in Pydantic 2.11.
                # It catches the resulting exception so that nothing bubbles up here that can be tested.
                warnings.simplefilter('ignore')
                result = await Runner.run(agent, 'Give me a random number')
            assert result.final_output == snapshot("Here's a random number for you: 4")

    assert simplify_spans(exporter.exported_spans_as_dict(parse_json_attributes=True)) == snapshot(
        [
            {
                'name': 'MCP request: initialize',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 2000000000,
                'attributes': {
                    'code.filepath': 'test_openai_agents_mcp.py',
                    'code.function': 'test_mcp',
                    'code.lineno': 123,
                    'request': {
                        'method': 'initialize',
                        'params': {
                            'meta': None,
                            'protocolVersion': IsStr(),
                            'capabilities': {
                                'experimental': None,
                                'sampling': None,
                                'elicitation': None,
                                'roots': None,
                            },
                            'clientInfo': {'name': 'mcp', 'title': None, 'version': '0.1.0'},
                        },
                    },
                    'rpc.system': 'jsonrpc',
                    'rpc.jsonrpc.version': '2.0',
                    'rpc.method': 'initialize',
                    'logfire.msg_template': 'MCP request: initialize',
                    'logfire.msg': 'MCP request: initialize',
                    'logfire.span_type': 'span',
                    'response': {
                        'meta': None,
                        'protocolVersion': IsStr(),
                        'capabilities': {
                            'experimental': {},
                            'logging': None,
                            'prompts': {'listChanged': False},
                            'resources': {'subscribe': False, 'listChanged': False},
                            'tools': {'listChanged': False},
                            'completions': None,
                        },
                        'serverInfo': {'name': 'FastMCP', 'title': None, 'version': IsStr()},
                        'instructions': None,
                    },
                },
            },
            {
                'name': 'MCP server handle request: tools/list',
                'context': {'trace_id': 2, 'span_id': 9, 'is_remote': False},
                'parent': {'trace_id': 2, 'span_id': 7, 'is_remote': True},
                'start_time': 6000000000,
                'end_time': 7000000000,
                'attributes': {
                    'request': {
                        'method': 'tools/list',
                        'params': {
                            'meta': {
                                'progressToken': None,
                                'traceparent': '00-00000000000000000000000000000002-0000000000000007-01',
                            },
                            'cursor': None,
                        },
                        'jsonrpc': '2.0',
                        'id': 1,
                    },
                    'logfire.msg_template': 'MCP server handle request: tools/list',
                    'logfire.msg': 'MCP server handle request: tools/list',
                    'logfire.span_type': 'span',
                },
            },
            {
                'name': 'MCP request: tools/list',
                'context': {'trace_id': 2, 'span_id': 7, 'is_remote': False},
                'parent': {'trace_id': 2, 'span_id': 5, 'is_remote': False},
                'start_time': 5000000000,
                'end_time': 8000000000,
                'attributes': {
                    'code.filepath': 'test_openai_agents_mcp.py',
                    'code.function': 'test_mcp',
                    'code.lineno': 123,
                    'request': {
                        'method': 'tools/list',
                        'params': None,
                    },
                    'rpc.system': 'jsonrpc',
                    'rpc.jsonrpc.version': '2.0',
                    'rpc.method': 'tools/list',
                    'logfire.msg_template': 'MCP request: tools/list',
                    'logfire.msg': 'MCP request: tools/list',
                    'logfire.span_type': 'span',
                    'response': {
                        'meta': None,
                        'nextCursor': None,
                        'tools': [
                            {
                                'name': 'random_number',
                                'title': None,
                                'description': '',
                                'inputSchema': {'properties': {}, 'title': 'random_numberArguments', 'type': 'object'},
                                'outputSchema': {
                                    'properties': {'result': {'title': 'Result', 'type': 'integer'}},
                                    'required': ['result'],
                                    'title': 'random_numberOutput',
                                    'type': 'object',
                                },
                                'annotations': None,
                                'meta': None,
                            }
                        ],
                    },
                },
            },
            {
                'name': 'MCP: list tools from server {server}',
                'context': {'trace_id': 2, 'span_id': 5, 'is_remote': False},
                'parent': {'trace_id': 2, 'span_id': 3, 'is_remote': False},
                'start_time': 4000000000,
                'end_time': 9000000000,
                'attributes': {
                    'code.filepath': 'test_openai_agents_mcp.py',
                    'code.function': 'test_mcp',
                    'code.lineno': 123,
                    'logfire.msg_template': 'MCP: list tools from server {server}',
                    'logfire.span_type': 'span',
                    'server': 'MyMCPServer',
                    'result': ['random_number'],
                    'gen_ai.system': 'openai',
                    'logfire.msg': 'MCP: list tools from server MyMCPServer',
                },
            },
            {
                'name': 'Responses API with {gen_ai.request.model!r}',
                'context': {'trace_id': 2, 'span_id': 13, 'is_remote': False},
                'parent': {'trace_id': 2, 'span_id': 11, 'is_remote': False},
                'start_time': 11000000000,
                'end_time': 12000000000,
                'attributes': {
                    'gen_ai.request.model': 'gpt-4o',
                    'logfire.msg_template': 'Responses API with {gen_ai.request.model!r}',
                    'logfire.span_type': 'span',
                    'response_id': 'resp_67e6908455c48191a9de5131e91abcb805b6a918ffc4827a',
                    'gen_ai.system': 'openai',
                    'gen_ai.response.model': 'gpt-4o-2024-08-06',
                    'gen_ai.operation.name': 'chat',
                    'raw_input': [{'content': 'Give me a random number', 'role': 'user'}],
                    'events': [
                        {'event.name': 'gen_ai.user.message', 'content': 'Give me a random number', 'role': 'user'},
                        {
                            'event.name': 'gen_ai.assistant.message',
                            'role': 'assistant',
                            'tool_calls': [
                                {
                                    'id': 'call_jfYaCkab5PQtyNrcrSgMdlRf',
                                    'type': 'function',
                                    'function': {'name': 'random_number', 'arguments': '{}'},
                                }
                            ],
                        },
                    ],
                    'gen_ai.usage.input_tokens': 51,
                    'gen_ai.usage.output_tokens': 11,
                    'logfire.msg': "Responses API with 'gpt-4o'",
                },
            },
            {
                'name': 'MCP server log',
                'context': {'trace_id': 2, 'span_id': 21, 'is_remote': False},
                'parent': {'trace_id': 2, 'span_id': 19, 'is_remote': True},
                'start_time': 16000000000,
                'end_time': 16000000000,
                'attributes': {
                    'logfire.span_type': 'log',
                    'logfire.level_num': 9,
                    'logfire.msg_template': 'MCP server log',
                    'logfire.msg': 'MCP server log',
                    'data': 'Generating a random number',
                },
            },
            {
                'name': 'MCP server log from my_logger',
                'context': {'trace_id': 2, 'span_id': 22, 'is_remote': False},
                'parent': {'trace_id': 2, 'span_id': 19, 'is_remote': True},
                'start_time': 17000000000,
                'end_time': 17000000000,
                'attributes': {
                    'logfire.span_type': 'log',
                    'logfire.level_num': 21,
                    'logfire.msg_template': 'MCP server log from my_logger',
                    'logfire.msg': 'MCP server log from my_logger',
                    'data': 'Dice broken! Improvising...',
                },
            },
            {
                'name': 'MCP server handle request: tools/call',
                'context': {'trace_id': 2, 'span_id': 19, 'is_remote': False},
                'parent': {'trace_id': 2, 'span_id': 17, 'is_remote': True},
                'start_time': 15000000000,
                'end_time': 18000000000,
                'attributes': {
                    'request': {
                        'method': 'tools/call',
                        'params': {
                            'meta': {
                                'progressToken': None,
                                'traceparent': '00-00000000000000000000000000000002-0000000000000011-01',
                            },
                            'name': 'random_number',
                            'arguments': {},
                        },
                        'jsonrpc': '2.0',
                        'id': 2,
                    },
                    'logfire.msg_template': 'MCP server handle request: tools/call',
                    'logfire.msg': 'MCP server handle request: tools/call',
                    'logfire.span_type': 'span',
                },
            },
            {
                'name': 'MCP request: tools/call random_number',
                'context': {'trace_id': 2, 'span_id': 17, 'is_remote': False},
                'parent': {'trace_id': 2, 'span_id': 15, 'is_remote': False},
                'start_time': 14000000000,
                'end_time': 19000000000,
                'attributes': {
                    'request': {
                        'method': 'tools/call',
                        'params': {'meta': None, 'name': 'random_number', 'arguments': {}},
                    },
                    'rpc.system': 'jsonrpc',
                    'rpc.jsonrpc.version': '2.0',
                    'rpc.method': 'tools/call',
                    'logfire.msg_template': 'MCP request: tools/call random_number',
                    'logfire.msg': 'MCP request: tools/call random_number',
                    'logfire.span_type': 'span',
                    'response': {
                        'meta': None,
                        'content': [{'type': 'text', 'text': '4', 'annotations': None, 'meta': None}],
                        'structuredContent': {'result': 4},
                        'isError': False,
                    },
                },
            },
            {
                'name': 'Function: {name}',
                'context': {'trace_id': 2, 'span_id': 15, 'is_remote': False},
                'parent': {'trace_id': 2, 'span_id': 11, 'is_remote': False},
                'start_time': 13000000000,
                'end_time': 20000000000,
                'attributes': {
                    'logfire.msg_template': 'Function: {name}',
                    'logfire.span_type': 'span',
                    'name': 'random_number',
                    'input': {},
                    'output': {'type': 'text', 'text': '4', 'annotations': None, 'meta': None},
                    'mcp_data': {'server': 'MyMCPServer'},
                    'gen_ai.system': 'openai',
                    'logfire.msg': 'Function: random_number',
                },
            },
            {
                'name': 'MCP server handle request: tools/list',
                'context': {'trace_id': 2, 'span_id': 27, 'is_remote': False},
                'parent': {'trace_id': 2, 'span_id': 25, 'is_remote': True},
                'start_time': 23000000000,
                'end_time': 24000000000,
                'attributes': {
                    'request': {
                        'method': 'tools/list',
                        'params': {
                            'meta': {
                                'progressToken': None,
                                'traceparent': '00-00000000000000000000000000000002-0000000000000019-01',
                            },
                            'cursor': None,
                        },
                        'jsonrpc': '2.0',
                        'id': 3,
                    },
                    'logfire.msg_template': 'MCP server handle request: tools/list',
                    'logfire.msg': 'MCP server handle request: tools/list',
                    'logfire.span_type': 'span',
                },
            },
            {
                'name': 'MCP request: tools/list',
                'context': {'trace_id': 2, 'span_id': 25, 'is_remote': False},
                'parent': {'trace_id': 2, 'span_id': 23, 'is_remote': False},
                'start_time': 22000000000,
                'end_time': 25000000000,
                'attributes': {
                    'code.filepath': 'test_openai_agents_mcp.py',
                    'code.function': 'test_mcp',
                    'code.lineno': 123,
                    'request': {'method': 'tools/list', 'params': None},
                    'rpc.system': 'jsonrpc',
                    'rpc.jsonrpc.version': '2.0',
                    'rpc.method': 'tools/list',
                    'logfire.msg_template': 'MCP request: tools/list',
                    'logfire.msg': 'MCP request: tools/list',
                    'logfire.span_type': 'span',
                    'response': {
                        'meta': None,
                        'nextCursor': None,
                        'tools': [
                            {
                                'name': 'random_number',
                                'title': None,
                                'description': '',
                                'inputSchema': {'properties': {}, 'title': 'random_numberArguments', 'type': 'object'},
                                'outputSchema': {
                                    'properties': {'result': {'title': 'Result', 'type': 'integer'}},
                                    'required': ['result'],
                                    'title': 'random_numberOutput',
                                    'type': 'object',
                                },
                                'annotations': None,
                                'meta': None,
                            }
                        ],
                    },
                },
            },
            {
                'name': 'MCP: list tools from server {server}',
                'context': {'trace_id': 2, 'span_id': 23, 'is_remote': False},
                'parent': {'trace_id': 2, 'span_id': 11, 'is_remote': False},
                'start_time': 21000000000,
                'end_time': 26000000000,
                'attributes': {
                    'code.filepath': 'test_openai_agents_mcp.py',
                    'code.function': 'test_mcp',
                    'code.lineno': 123,
                    'logfire.msg_template': 'MCP: list tools from server {server}',
                    'logfire.span_type': 'span',
                    'server': 'MyMCPServer',
                    'result': ['random_number'],
                    'gen_ai.system': 'openai',
                    'logfire.msg': 'MCP: list tools from server MyMCPServer',
                },
            },
            {
                'name': 'Responses API with {gen_ai.request.model!r}',
                'context': {'trace_id': 2, 'span_id': 29, 'is_remote': False},
                'parent': {'trace_id': 2, 'span_id': 11, 'is_remote': False},
                'start_time': 27000000000,
                'end_time': 28000000000,
                'attributes': {
                    'code.filepath': 'test_openai_agents_mcp.py',
                    'code.function': 'test_mcp',
                    'code.lineno': 123,
                    'gen_ai.request.model': 'gpt-4o',
                    'logfire.msg_template': 'Responses API with {gen_ai.request.model!r}',
                    'logfire.span_type': 'span',
                    'response_id': 'resp_67e6908542b08191a02609780bb4c28205b6a918ffc4827a',
                    'gen_ai.system': 'openai',
                    'gen_ai.response.model': 'gpt-4o-2024-08-06',
                    'gen_ai.operation.name': 'chat',
                    'raw_input': [
                        {'content': 'Give me a random number', 'role': 'user'},
                        {
                            'arguments': '{}',
                            'call_id': 'call_jfYaCkab5PQtyNrcrSgMdlRf',
                            'name': 'random_number',
                            'type': 'function_call',
                            'id': 'fc_67e69084b6188191bba33a5f67ac345b05b6a918ffc4827a',
                            'status': 'completed',
                        },
                        {
                            'call_id': 'call_jfYaCkab5PQtyNrcrSgMdlRf',
                            'output': '{"type":"text","text":"4","annotations":null,"meta":null}',
                            'type': 'function_call_output',
                        },
                    ],
                    'events': [
                        {'event.name': 'gen_ai.user.message', 'content': 'Give me a random number', 'role': 'user'},
                        {
                            'event.name': 'gen_ai.assistant.message',
                            'role': 'assistant',
                            'tool_calls': [
                                {
                                    'id': 'call_jfYaCkab5PQtyNrcrSgMdlRf',
                                    'type': 'function',
                                    'function': {'name': 'random_number', 'arguments': '{}'},
                                }
                            ],
                        },
                        {
                            'event.name': 'gen_ai.tool.message',
                            'role': 'tool',
                            'id': 'call_jfYaCkab5PQtyNrcrSgMdlRf',
                            'content': '{"type":"text","text":"4","annotations":null,"meta":null}',
                            'name': 'random_number',
                        },
                        {
                            'event.name': 'gen_ai.assistant.message',
                            'content': "Here's a random number for you: 4",
                            'role': 'assistant',
                        },
                    ],
                    'gen_ai.usage.input_tokens': 83,
                    'gen_ai.usage.output_tokens': 11,
                    'logfire.msg': "Responses API with 'gpt-4o'",
                },
            },
            {
                'name': 'Agent run: {name!r}',
                'context': {'trace_id': 2, 'span_id': 11, 'is_remote': False},
                'parent': {'trace_id': 2, 'span_id': 3, 'is_remote': False},
                'start_time': 10000000000,
                'end_time': 29000000000,
                'attributes': {
                    'code.filepath': 'test_openai_agents_mcp.py',
                    'code.function': 'test_mcp',
                    'code.lineno': 123,
                    'logfire.msg_template': 'Agent run: {name!r}',
                    'logfire.span_type': 'span',
                    'name': 'Assistant',
                    'handoffs': [],
                    'tools': ['random_number'],
                    'output_type': 'str',
                    'gen_ai.system': 'openai',
                    'logfire.msg': "Agent run: 'Assistant'",
                },
            },
            {
                'name': 'OpenAI Agents trace: {name}',
                'context': {'trace_id': 2, 'span_id': 3, 'is_remote': False},
                'parent': None,
                'start_time': 3000000000,
                'end_time': 30000000000,
                'attributes': {
                    'code.filepath': 'test_openai_agents_mcp.py',
                    'code.function': 'test_mcp',
                    'code.lineno': 123,
                    'name': 'my_trace',
                    'group_id': 'null',
                    'metadata': 'null',
                    'logfire.msg_template': 'OpenAI Agents trace: {name}',
                    'logfire.msg': 'OpenAI Agents trace: my_trace',
                    'logfire.span_type': 'span',
                    'agent_trace_id': 'trace_123',
                },
            },
        ]
    )
