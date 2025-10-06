# No from __future__ import annotations here
# because it breaks `ctx: Context` being recognised by `@fastmcp.tool()` properly.

import asyncio
import os
import sys
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

import pydantic
import pytest
from dirty_equals import IsPartialDict

import logfire
from logfire._internal.exporters.test import TestExporter
from logfire._internal.utils import get_version
from tests.otel_integrations.test_openai_agents import simplify_spans

try:
    from inline_snapshot import snapshot
    from mcp.server.fastmcp import Context, FastMCP
    from mcp.shared.memory import create_client_server_memory_streams
    from pydantic_ai import Agent
    from pydantic_ai.mcp import MCPServer
    from pydantic_ai.models.mcp_sampling import MCPSamplingModel
except Exception:
    assert not TYPE_CHECKING


pytestmark = [
    pytest.mark.skipif(sys.version_info < (3, 10), reason='MCP requires Python 3.10 or higher'),
    pytest.mark.skipif(
        get_version(pydantic.__version__) < get_version('2.10'), reason='Pydantic AI requires Pydantic 2.10 or higher'
    ),
]

os.environ.setdefault('OPENAI_API_KEY', 'foo')


@pytest.mark.vcr()
@pytest.mark.anyio
async def test_pydantic_ai_mcp_sampling(exporter: TestExporter):
    logfire.instrument_pydantic_ai(version=3)

    fastmcp = FastMCP()

    @fastmcp.tool()
    async def joker(ctx: Context, theme: str) -> str:  # type: ignore
        """Poem generator"""
        r = await Agent().run(f'tell a joke about {theme}', model=MCPSamplingModel(session=ctx.session))
        return r.output

    async with create_client_server_memory_streams() as (client_streams, server_streams):
        lowlevel_mcp = fastmcp._mcp_server  # type: ignore
        asyncio.create_task(
            lowlevel_mcp.run(
                *server_streams,
                lowlevel_mcp.create_initialization_options(),
                raise_exceptions=True,
            )
        )

        class MyMCPServer(MCPServer):
            @asynccontextmanager
            async def client_streams(self):
                yield client_streams

        agent = Agent('openai:gpt-4o', toolsets=[MyMCPServer()])
        async with agent:
            agent.set_mcp_sampling_model()
            result = await agent.run('tell a joke about socks')
            assert result.output == snapshot("""\
Why did the sock break up with the shoe?

Because it found something more "sole-ful!"\
""")

    assert simplify_spans(exporter.exported_spans_as_dict(parse_json_attributes=True)) == snapshot(
        [
            {
                'name': 'MCP request: initialize',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 2000000000,
                'attributes': {
                    'code.filepath': 'test_pydantic_ai_mcp.py',
                    'code.function': 'test_pydantic_ai_mcp_sampling',
                    'code.lineno': 123,
                    'request': {
                        'method': 'initialize',
                        'params': IsPartialDict(),
                    },
                    'rpc.system': 'jsonrpc',
                    'rpc.jsonrpc.version': '2.0',
                    'rpc.method': 'initialize',
                    'logfire.msg_template': 'MCP request: initialize',
                    'logfire.msg': 'MCP request: initialize',
                    'logfire.span_type': 'span',
                    'response': IsPartialDict(),
                },
            },
            {
                'name': 'MCP server handle request: tools/list',
                'context': {'trace_id': 2, 'span_id': 7, 'is_remote': False},
                'parent': {'trace_id': 2, 'span_id': 5, 'is_remote': True},
                'start_time': 5000000000,
                'end_time': 6000000000,
                'attributes': {
                    'request': {
                        'method': 'tools/list',
                        'params': {
                            'meta': {
                                'progressToken': None,
                                'traceparent': '00-00000000000000000000000000000002-0000000000000005-01',
                            },
                            'cursor': None,
                        },
                        'jsonrpc': '2.0',
                        'id': 1,
                    },
                    'logfire.msg_template': 'MCP server handle request: tools/list',
                    'logfire.msg': 'MCP server handle request: tools/list',
                    'logfire.span_type': 'span',
                    'response': {
                        'meta': None,
                        'nextCursor': None,
                        'tools': [IsPartialDict()],
                    },
                },
            },
            {
                'name': 'MCP request: tools/list',
                'context': {'trace_id': 2, 'span_id': 5, 'is_remote': False},
                'parent': {'trace_id': 2, 'span_id': 3, 'is_remote': False},
                'start_time': 4000000000,
                'end_time': 7000000000,
                'attributes': {
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
                        'tools': [IsPartialDict()],
                    },
                },
            },
            {
                'name': 'chat gpt-4o',
                'context': {'trace_id': 2, 'span_id': 9, 'is_remote': False},
                'parent': {'trace_id': 2, 'span_id': 3, 'is_remote': False},
                'start_time': 8000000000,
                'end_time': 9000000000,
                'attributes': {
                    'gen_ai.operation.name': 'chat',
                    'gen_ai.system': 'openai',
                    'gen_ai.request.model': 'gpt-4o',
                    'server.address': 'api.openai.com',
                    'model_request_parameters': IsPartialDict(),
                    'logfire.span_type': 'span',
                    'logfire.msg': 'chat gpt-4o',
                    'gen_ai.input.messages': [
                        {'role': 'user', 'parts': [{'type': 'text', 'content': 'tell a joke about socks'}]}
                    ],
                    'gen_ai.output.messages': [
                        {
                            'role': 'assistant',
                            'parts': [
                                {
                                    'type': 'tool_call',
                                    'id': 'call_YWeIZ4oGGwEnk9GIb443ZNys',
                                    'name': 'joker',
                                    'arguments': '{"theme":"socks"}',
                                }
                            ],
                            'finish_reason': 'tool_call',
                        }
                    ],
                    'gen_ai.usage.input_tokens': 45,
                    'gen_ai.usage.output_tokens': 15,
                    'gen_ai.response.model': 'gpt-4o-2024-08-06',
                    'operation.cost': 0.0002625,
                    'gen_ai.response.id': 'chatcmpl-CB4UKZ6j6biTXLnSyuCu15BPxKHT8',
                    'gen_ai.response.finish_reasons': ('tool_call',),
                },
            },
            {
                'name': 'chat gpt-4o',
                'context': {'trace_id': 2, 'span_id': 27, 'is_remote': False},
                'parent': {'trace_id': 2, 'span_id': 25, 'is_remote': False},
                'start_time': 18000000000,
                'end_time': 19000000000,
                'attributes': {
                    'gen_ai.operation.name': 'chat',
                    'gen_ai.system': 'openai',
                    'gen_ai.request.model': 'gpt-4o',
                    'server.address': 'api.openai.com',
                    'model_request_parameters': IsPartialDict(),
                    'gen_ai.request.max_tokens': 16384,
                    'logfire.span_type': 'span',
                    'logfire.msg': 'chat gpt-4o',
                    'gen_ai.input.messages': [
                        {'role': 'user', 'parts': [{'type': 'text', 'content': 'tell a joke about socks'}]}
                    ],
                    'gen_ai.output.messages': [
                        {
                            'role': 'assistant',
                            'parts': [
                                {
                                    'type': 'text',
                                    'content': """\
Why did the sock break up with the shoe?

Because it found something more "sole-ful!"\
""",
                                }
                            ],
                            'finish_reason': 'stop',
                        }
                    ],
                    'gen_ai.usage.input_tokens': 12,
                    'gen_ai.usage.output_tokens': 20,
                    'gen_ai.response.model': 'gpt-4o-2024-08-06',
                    'operation.cost': 0.00023,
                    'gen_ai.response.id': 'chatcmpl-CB4UMeutkPM3KsHUypidgbENPki0v',
                    'gen_ai.response.finish_reasons': ('stop',),
                },
            },
            {
                'name': 'MCP client handle request: sampling/createMessage',
                'context': {'trace_id': 2, 'span_id': 25, 'is_remote': False},
                'parent': {'trace_id': 2, 'span_id': 23, 'is_remote': True},
                'start_time': 17000000000,
                'end_time': 20000000000,
                'attributes': {
                    'request': {
                        'method': 'sampling/createMessage',
                        'params': {
                            'meta': {
                                'progressToken': None,
                                'traceparent': '00-00000000000000000000000000000002-0000000000000017-01',
                            },
                            'messages': [
                                {
                                    'role': 'user',
                                    'content': {
                                        'type': 'text',
                                        'text': 'tell a joke about socks',
                                        'annotations': None,
                                        'meta': None,
                                    },
                                }
                            ],
                            'modelPreferences': None,
                            'systemPrompt': '',
                            'includeContext': None,
                            'temperature': None,
                            'maxTokens': 16384,
                            'stopSequences': None,
                            'metadata': None,
                        },
                        'jsonrpc': '2.0',
                        'id': 0,
                    },
                    'logfire.msg_template': 'MCP client handle request: sampling/createMessage',
                    'logfire.msg': 'MCP client handle request: sampling/createMessage',
                    'logfire.span_type': 'span',
                    'response': {
                        'meta': None,
                        'role': 'assistant',
                        'content': {
                            'type': 'text',
                            'text': """\
Why did the sock break up with the shoe?

Because it found something more "sole-ful!"\
""",
                            'annotations': None,
                            'meta': None,
                        },
                        'model': 'gpt-4o',
                        'stopReason': None,
                    },
                },
            },
            {
                'name': 'MCP request: sampling/createMessage',
                'context': {'trace_id': 2, 'span_id': 23, 'is_remote': False},
                'parent': {'trace_id': 2, 'span_id': 21, 'is_remote': False},
                'start_time': 16000000000,
                'end_time': 21000000000,
                'attributes': {
                    'code.filepath': 'test_pydantic_ai_mcp.py',
                    'code.function': 'joker',
                    'code.lineno': 123,
                    'request': {
                        'method': 'sampling/createMessage',
                        'params': {
                            'meta': None,
                            'messages': [
                                {
                                    'role': 'user',
                                    'content': {
                                        'type': 'text',
                                        'text': 'tell a joke about socks',
                                        'annotations': None,
                                        'meta': None,
                                    },
                                }
                            ],
                            'modelPreferences': None,
                            'systemPrompt': '',
                            'includeContext': None,
                            'temperature': None,
                            'maxTokens': 16384,
                            'stopSequences': None,
                            'metadata': None,
                        },
                    },
                    'rpc.system': 'jsonrpc',
                    'rpc.jsonrpc.version': '2.0',
                    'rpc.method': 'sampling/createMessage',
                    'logfire.msg_template': 'MCP request: sampling/createMessage',
                    'logfire.msg': 'MCP request: sampling/createMessage',
                    'logfire.span_type': 'span',
                    'response': {
                        'meta': None,
                        'role': 'assistant',
                        'content': {
                            'type': 'text',
                            'text': """\
Why did the sock break up with the shoe?

Because it found something more "sole-ful!"\
""",
                            'annotations': None,
                            'meta': None,
                        },
                        'model': 'gpt-4o',
                        'stopReason': None,
                    },
                },
            },
            {
                'name': 'chat mcp-sampling',
                'context': {'trace_id': 2, 'span_id': 21, 'is_remote': False},
                'parent': {'trace_id': 2, 'span_id': 19, 'is_remote': False},
                'start_time': 15000000000,
                'end_time': 22000000000,
                'attributes': {
                    'gen_ai.operation.name': 'chat',
                    'gen_ai.system': 'MCP',
                    'gen_ai.request.model': 'mcp-sampling',
                    'model_request_parameters': IsPartialDict(),
                    'logfire.span_type': 'span',
                    'logfire.msg': 'chat mcp-sampling',
                    'gen_ai.input.messages': [
                        {'role': 'user', 'parts': [{'type': 'text', 'content': 'tell a joke about socks'}]}
                    ],
                    'gen_ai.output.messages': [
                        {
                            'role': 'assistant',
                            'parts': [
                                {
                                    'type': 'text',
                                    'content': """\
Why did the sock break up with the shoe?

Because it found something more "sole-ful!"\
""",
                                }
                            ],
                        }
                    ],
                    'gen_ai.response.model': 'gpt-4o',
                    'operation.cost': 0.0,
                },
            },
            {
                'name': 'invoke_agent agent',
                'context': {'trace_id': 2, 'span_id': 19, 'is_remote': False},
                'parent': {'trace_id': 2, 'span_id': 17, 'is_remote': False},
                'start_time': 14000000000,
                'end_time': 23000000000,
                'attributes': {
                    'model_name': 'mcp-sampling',
                    'agent_name': 'agent',
                    'gen_ai.agent.name': 'agent',
                    'logfire.msg': 'agent run',
                    'logfire.span_type': 'span',
                    'final_result': """\
Why did the sock break up with the shoe?

Because it found something more "sole-ful!"\
""",
                    'pydantic_ai.all_messages': [
                        {'role': 'user', 'parts': [{'type': 'text', 'content': 'tell a joke about socks'}]},
                        {
                            'role': 'assistant',
                            'parts': [
                                {
                                    'type': 'text',
                                    'content': """\
Why did the sock break up with the shoe?

Because it found something more "sole-ful!"\
""",
                                }
                            ],
                        },
                    ],
                },
            },
            {
                'name': 'MCP server handle request: tools/call',
                'context': {'trace_id': 2, 'span_id': 17, 'is_remote': False},
                'parent': {'trace_id': 2, 'span_id': 15, 'is_remote': True},
                'start_time': 13000000000,
                'end_time': 24000000000,
                'attributes': {
                    'request': {
                        'method': 'tools/call',
                        'params': {
                            'meta': {
                                'progressToken': None,
                                'traceparent': '00-00000000000000000000000000000002-000000000000000f-01',
                            },
                            'name': 'joker',
                            'arguments': {'theme': 'socks'},
                        },
                        'jsonrpc': '2.0',
                        'id': 2,
                    },
                    'logfire.msg_template': 'MCP server handle request: tools/call',
                    'logfire.msg': 'MCP server handle request: tools/call',
                    'logfire.span_type': 'span',
                    'response': {
                        'meta': None,
                        'content': [
                            {
                                'type': 'text',
                                'text': """\
Why did the sock break up with the shoe?

Because it found something more "sole-ful!"\
""",
                                'annotations': None,
                                'meta': None,
                            }
                        ],
                        'structuredContent': {
                            'result': """\
Why did the sock break up with the shoe?

Because it found something more "sole-ful!"\
"""
                        },
                        'isError': False,
                    },
                },
            },
            {
                'name': 'MCP request: tools/call joker',
                'context': {'trace_id': 2, 'span_id': 15, 'is_remote': False},
                'parent': {'trace_id': 2, 'span_id': 13, 'is_remote': False},
                'start_time': 12000000000,
                'end_time': 25000000000,
                'attributes': {
                    'request': {
                        'method': 'tools/call',
                        'params': {'meta': None, 'name': 'joker', 'arguments': {'theme': 'socks'}},
                    },
                    'rpc.system': 'jsonrpc',
                    'rpc.jsonrpc.version': '2.0',
                    'rpc.method': 'tools/call',
                    'logfire.msg_template': 'MCP request: tools/call joker',
                    'logfire.msg': 'MCP request: tools/call joker',
                    'logfire.span_type': 'span',
                    'response': {
                        'meta': None,
                        'content': [
                            {
                                'type': 'text',
                                'text': """\
Why did the sock break up with the shoe?

Because it found something more "sole-ful!"\
""",
                                'annotations': None,
                                'meta': None,
                            }
                        ],
                        'structuredContent': {
                            'result': """\
Why did the sock break up with the shoe?

Because it found something more "sole-ful!"\
"""
                        },
                        'isError': False,
                    },
                },
            },
            {
                'name': 'execute_tool joker',
                'context': {'trace_id': 2, 'span_id': 13, 'is_remote': False},
                'parent': {'trace_id': 2, 'span_id': 11, 'is_remote': False},
                'start_time': 11000000000,
                'end_time': 26000000000,
                'attributes': {
                    'gen_ai.tool.name': 'joker',
                    'gen_ai.tool.call.id': 'call_YWeIZ4oGGwEnk9GIb443ZNys',
                    'gen_ai.tool.call.arguments': {'theme': 'socks'},
                    'logfire.msg': 'running tool: joker',
                    'logfire.span_type': 'span',
                    'gen_ai.tool.call.result': """\
Why did the sock break up with the shoe?

Because it found something more "sole-ful!"\
""",
                },
            },
            {
                'name': 'running tools',
                'context': {'trace_id': 2, 'span_id': 11, 'is_remote': False},
                'parent': {'trace_id': 2, 'span_id': 3, 'is_remote': False},
                'start_time': 10000000000,
                'end_time': 27000000000,
                'attributes': {'tools': ('joker',), 'logfire.msg': 'running 1 tool', 'logfire.span_type': 'span'},
            },
            {
                'name': 'MCP server handle request: tools/list',
                'context': {'trace_id': 2, 'span_id': 31, 'is_remote': False},
                'parent': {'trace_id': 2, 'span_id': 29, 'is_remote': True},
                'start_time': 29000000000,
                'end_time': 30000000000,
                'attributes': {
                    'request': {
                        'method': 'tools/list',
                        'params': {
                            'meta': {
                                'progressToken': None,
                                'traceparent': '00-00000000000000000000000000000002-000000000000001d-01',
                            },
                            'cursor': None,
                        },
                        'jsonrpc': '2.0',
                        'id': 3,
                    },
                    'logfire.msg_template': 'MCP server handle request: tools/list',
                    'logfire.msg': 'MCP server handle request: tools/list',
                    'logfire.span_type': 'span',
                    'response': {
                        'meta': None,
                        'nextCursor': None,
                        'tools': [IsPartialDict()],
                    },
                },
            },
            {
                'name': 'MCP request: tools/list',
                'context': {'trace_id': 2, 'span_id': 29, 'is_remote': False},
                'parent': {'trace_id': 2, 'span_id': 3, 'is_remote': False},
                'start_time': 28000000000,
                'end_time': 31000000000,
                'attributes': {
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
                        'tools': [IsPartialDict()],
                    },
                },
            },
            {
                'name': 'chat gpt-4o',
                'context': {'trace_id': 2, 'span_id': 33, 'is_remote': False},
                'parent': {'trace_id': 2, 'span_id': 3, 'is_remote': False},
                'start_time': 32000000000,
                'end_time': 33000000000,
                'attributes': {
                    'gen_ai.operation.name': 'chat',
                    'gen_ai.system': 'openai',
                    'gen_ai.request.model': 'gpt-4o',
                    'server.address': 'api.openai.com',
                    'model_request_parameters': IsPartialDict(),
                    'logfire.span_type': 'span',
                    'logfire.msg': 'chat gpt-4o',
                    'gen_ai.input.messages': [
                        {'role': 'user', 'parts': [{'type': 'text', 'content': 'tell a joke about socks'}]},
                        {
                            'role': 'assistant',
                            'parts': [
                                {
                                    'type': 'tool_call',
                                    'id': 'call_YWeIZ4oGGwEnk9GIb443ZNys',
                                    'name': 'joker',
                                    'arguments': '{"theme":"socks"}',
                                }
                            ],
                            'finish_reason': 'tool_call',
                        },
                        {
                            'role': 'user',
                            'parts': [
                                {
                                    'type': 'tool_call_response',
                                    'id': 'call_YWeIZ4oGGwEnk9GIb443ZNys',
                                    'name': 'joker',
                                    'result': """\
Why did the sock break up with the shoe?

Because it found something more "sole-ful!"\
""",
                                }
                            ],
                        },
                    ],
                    'gen_ai.output.messages': [
                        {
                            'role': 'assistant',
                            'parts': [
                                {
                                    'type': 'text',
                                    'content': """\
Why did the sock break up with the shoe?

Because it found something more "sole-ful!"\
""",
                                }
                            ],
                            'finish_reason': 'stop',
                        }
                    ],
                    'gen_ai.usage.input_tokens': 87,
                    'gen_ai.usage.output_tokens': 21,
                    'gen_ai.response.model': 'gpt-4o-2024-08-06',
                    'operation.cost': 0.0004275,
                    'gen_ai.response.id': 'chatcmpl-CB4UNlU07HRfa3dlbjeCwGhyUxFxV',
                    'gen_ai.response.finish_reasons': ('stop',),
                },
            },
            {
                'name': 'invoke_agent agent',
                'context': {'trace_id': 2, 'span_id': 3, 'is_remote': False},
                'parent': None,
                'start_time': 3000000000,
                'end_time': 34000000000,
                'attributes': {
                    'model_name': 'gpt-4o',
                    'agent_name': 'agent',
                    'gen_ai.agent.name': 'agent',
                    'logfire.msg': 'agent run',
                    'logfire.span_type': 'span',
                    'final_result': """\
Why did the sock break up with the shoe?

Because it found something more "sole-ful!"\
""",
                    'gen_ai.usage.input_tokens': 132,
                    'gen_ai.usage.output_tokens': 36,
                    'pydantic_ai.all_messages': [
                        {'role': 'user', 'parts': [{'type': 'text', 'content': 'tell a joke about socks'}]},
                        {
                            'role': 'assistant',
                            'parts': [
                                {
                                    'type': 'tool_call',
                                    'id': 'call_YWeIZ4oGGwEnk9GIb443ZNys',
                                    'name': 'joker',
                                    'arguments': '{"theme":"socks"}',
                                }
                            ],
                            'finish_reason': 'tool_call',
                        },
                        {
                            'role': 'user',
                            'parts': [
                                {
                                    'type': 'tool_call_response',
                                    'id': 'call_YWeIZ4oGGwEnk9GIb443ZNys',
                                    'name': 'joker',
                                    'result': """\
Why did the sock break up with the shoe?

Because it found something more "sole-ful!"\
""",
                                }
                            ],
                        },
                        {
                            'role': 'assistant',
                            'parts': [
                                {
                                    'type': 'text',
                                    'content': """\
Why did the sock break up with the shoe?

Because it found something more "sole-ful!"\
""",
                                }
                            ],
                            'finish_reason': 'stop',
                        },
                    ],
                },
            },
        ]
    )
