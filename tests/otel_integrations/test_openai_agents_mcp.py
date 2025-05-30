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
from tests.otel_integrations.test_openai_agents import without_code_attrs

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

    assert without_code_attrs(exporter.exported_spans_as_dict(parse_json_attributes=True)) == snapshot(
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
                            'capabilities': {'experimental': None, 'sampling': None, 'roots': None},
                            'clientInfo': {'name': 'mcp', 'version': '0.1.0'},
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
                        },
                        'serverInfo': {'name': 'FastMCP', 'version': IsStr()},
                        'instructions': None,
                    },
                    'logfire.json_schema': {
                        'type': 'object',
                        'properties': {
                            'request': {
                                'type': 'object',
                                'title': 'ClientRequest',
                                'x-python-datatype': 'PydanticModel',
                                'properties': {
                                    'root': {
                                        'type': 'object',
                                        'title': 'InitializeRequest',
                                        'x-python-datatype': 'PydanticModel',
                                        'properties': {
                                            'params': {
                                                'type': 'object',
                                                'title': 'InitializeRequestParams',
                                                'x-python-datatype': 'PydanticModel',
                                                'properties': {
                                                    'capabilities': {
                                                        'type': 'object',
                                                        'title': 'ClientCapabilities',
                                                        'x-python-datatype': 'PydanticModel',
                                                    },
                                                    'clientInfo': {
                                                        'type': 'object',
                                                        'title': 'Implementation',
                                                        'x-python-datatype': 'PydanticModel',
                                                    },
                                                },
                                            }
                                        },
                                    }
                                },
                            },
                            'rpc.system': {},
                            'rpc.jsonrpc.version': {},
                            'rpc.method': {},
                            'response': {
                                'type': 'object',
                                'title': 'InitializeResult',
                                'x-python-datatype': 'PydanticModel',
                                'properties': {
                                    'capabilities': {
                                        'type': 'object',
                                        'title': 'ServerCapabilities',
                                        'x-python-datatype': 'PydanticModel',
                                        'properties': {
                                            'prompts': {
                                                'type': 'object',
                                                'title': 'PromptsCapability',
                                                'x-python-datatype': 'PydanticModel',
                                            },
                                            'resources': {
                                                'type': 'object',
                                                'title': 'ResourcesCapability',
                                                'x-python-datatype': 'PydanticModel',
                                            },
                                            'tools': {
                                                'type': 'object',
                                                'title': 'ToolsCapability',
                                                'x-python-datatype': 'PydanticModel',
                                            },
                                        },
                                    },
                                    'serverInfo': {
                                        'type': 'object',
                                        'title': 'Implementation',
                                        'x-python-datatype': 'PydanticModel',
                                    },
                                },
                            },
                        },
                    },
                },
            },
            {
                'name': 'MCP request: tools/list',
                'context': {'trace_id': 2, 'span_id': 9, 'is_remote': False},
                'parent': {'trace_id': 2, 'span_id': 7, 'is_remote': False},
                'start_time': 6000000000,
                'end_time': 7000000000,
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
                                'description': '',
                                'inputSchema': {'properties': {}, 'title': 'random_numberArguments', 'type': 'object'},
                                'annotations': None,
                            }
                        ],
                    },
                    'logfire.json_schema': {
                        'type': 'object',
                        'properties': {
                            'request': {
                                'type': 'object',
                                'title': 'ClientRequest',
                                'x-python-datatype': 'PydanticModel',
                                'properties': {
                                    'root': {
                                        'type': 'object',
                                        'title': 'ListToolsRequest',
                                        'x-python-datatype': 'PydanticModel',
                                    }
                                },
                            },
                            'rpc.system': {},
                            'rpc.jsonrpc.version': {},
                            'rpc.method': {},
                            'response': {
                                'type': 'object',
                                'title': 'ListToolsResult',
                                'x-python-datatype': 'PydanticModel',
                                'properties': {
                                    'tools': {
                                        'type': 'array',
                                        'items': {
                                            'type': 'object',
                                            'title': 'Tool',
                                            'x-python-datatype': 'PydanticModel',
                                        },
                                    }
                                },
                            },
                        },
                    },
                },
            },
            {
                'name': 'MCP: list tools from server {server}',
                'context': {'trace_id': 2, 'span_id': 7, 'is_remote': False},
                'parent': {'trace_id': 2, 'span_id': 5, 'is_remote': False},
                'start_time': 5000000000,
                'end_time': 8000000000,
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
                    'logfire.json_schema': {
                        'type': 'object',
                        'properties': {'server': {}, 'result': {'type': 'array'}, 'gen_ai.system': {}},
                    },
                },
            },
            {
                'name': 'Responses API with {gen_ai.request.model!r}',
                'context': {'trace_id': 2, 'span_id': 11, 'is_remote': False},
                'parent': {'trace_id': 2, 'span_id': 5, 'is_remote': False},
                'start_time': 9000000000,
                'end_time': 10000000000,
                'attributes': {
                    'model_settings': {
                        'temperature': None,
                        'top_p': None,
                        'frequency_penalty': None,
                        'presence_penalty': None,
                        'tool_choice': None,
                        'parallel_tool_calls': None,
                        'truncation': None,
                        'max_tokens': None,
                        'reasoning': None,
                        'metadata': None,
                        'store': None,
                        'include_usage': None,
                        'extra_query': None,
                        'extra_body': None,
                        'extra_headers': None,
                    },
                    'gen_ai.request.model': 'gpt-4o',
                    'logfire.msg_template': 'Responses API with {gen_ai.request.model!r}',
                    'logfire.span_type': 'span',
                    'response_id': 'resp_67e6908455c48191a9de5131e91abcb805b6a918ffc4827a',
                    'gen_ai.system': 'openai',
                    'gen_ai.response.model': 'gpt-4o-2024-08-06',
                    'response': {
                        'id': 'resp_67e6908455c48191a9de5131e91abcb805b6a918ffc4827a',
                        'created_at': 1743163524.0,
                        'error': None,
                        'incomplete_details': None,
                        'instructions': None,
                        'metadata': {},
                        'model': 'gpt-4o-2024-08-06',
                        'object': 'response',
                        'output': [
                            {
                                'arguments': '{}',
                                'call_id': 'call_jfYaCkab5PQtyNrcrSgMdlRf',
                                'name': 'random_number',
                                'type': 'function_call',
                                'id': 'fc_67e69084b6188191bba33a5f67ac345b05b6a918ffc4827a',
                                'status': 'completed',
                            }
                        ],
                        'parallel_tool_calls': False,
                        'temperature': 1.0,
                        'tool_choice': 'auto',
                        'tools': [
                            {
                                'name': 'random_number',
                                'parameters': {'properties': {}, 'title': 'random_numberArguments', 'type': 'object'},
                                'strict': False,
                                'type': 'function',
                                'description': None,
                            }
                        ],
                        'top_p': 1.0,
                        'background': None,
                        'max_output_tokens': None,
                        'previous_response_id': None,
                        'reasoning': {'effort': None, 'generate_summary': None, 'summary': None},
                        'service_tier': None,
                        'status': 'completed',
                        'text': {'format': {'type': 'text'}},
                        'truncation': 'disabled',
                        'usage': {
                            'input_tokens': 51,
                            'input_tokens_details': {'cached_tokens': 0},
                            'output_tokens': 11,
                            'output_tokens_details': {'reasoning_tokens': 0},
                            'total_tokens': 62,
                        },
                        'user': None,
                        'store': True,
                    },
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
                    'logfire.json_schema': {
                        'type': 'object',
                        'properties': {
                            'response_id': {},
                            'gen_ai.system': {},
                            'model_settings': {
                                'type': 'object',
                                'title': 'ModelSettings',
                                'x-python-datatype': 'dataclass',
                            },
                            'gen_ai.request.model': {},
                            'gen_ai.response.model': {},
                            'response': {
                                'type': 'object',
                                'title': 'Response',
                                'x-python-datatype': 'PydanticModel',
                                'properties': {
                                    'output': {
                                        'type': 'array',
                                        'items': {
                                            'type': 'object',
                                            'title': 'ResponseFunctionToolCall',
                                            'x-python-datatype': 'PydanticModel',
                                        },
                                    },
                                    'tools': {
                                        'type': 'array',
                                        'items': {
                                            'type': 'object',
                                            'title': 'FunctionTool',
                                            'x-python-datatype': 'PydanticModel',
                                        },
                                    },
                                    'reasoning': {
                                        'type': 'object',
                                        'title': 'Reasoning',
                                        'x-python-datatype': 'PydanticModel',
                                    },
                                    'text': {
                                        'type': 'object',
                                        'title': 'ResponseTextConfig',
                                        'x-python-datatype': 'PydanticModel',
                                        'properties': {
                                            'format': {
                                                'type': 'object',
                                                'title': 'ResponseFormatText',
                                                'x-python-datatype': 'PydanticModel',
                                            }
                                        },
                                    },
                                    'usage': {
                                        'type': 'object',
                                        'title': 'ResponseUsage',
                                        'x-python-datatype': 'PydanticModel',
                                        'properties': {
                                            'input_tokens_details': {
                                                'type': 'object',
                                                'title': 'InputTokensDetails',
                                                'x-python-datatype': 'PydanticModel',
                                            },
                                            'output_tokens_details': {
                                                'type': 'object',
                                                'title': 'OutputTokensDetails',
                                                'x-python-datatype': 'PydanticModel',
                                            },
                                        },
                                    },
                                },
                            },
                            'gen_ai.operation.name': {},
                            'raw_input': {'type': 'array'},
                            'events': {'type': 'array'},
                            'gen_ai.usage.input_tokens': {},
                            'gen_ai.usage.output_tokens': {},
                        },
                    },
                },
            },
            {
                'name': 'MCP server log',
                'context': {'trace_id': 3, 'span_id': 17, 'is_remote': False},
                'parent': None,
                'start_time': 13000000000,
                'end_time': 13000000000,
                'attributes': {
                    'logfire.span_type': 'log',
                    'logfire.level_num': 9,
                    'logfire.msg_template': 'MCP server log',
                    'logfire.msg': 'MCP server log',
                    'data': 'Generating a random number',
                    'logfire.json_schema': {'type': 'object', 'properties': {'data': {}}},
                },
            },
            {
                'name': 'MCP server log from my_logger',
                'context': {'trace_id': 4, 'span_id': 18, 'is_remote': False},
                'parent': None,
                'start_time': 14000000000,
                'end_time': 14000000000,
                'attributes': {
                    'logfire.span_type': 'log',
                    'logfire.level_num': 21,
                    'logfire.msg_template': 'MCP server log from my_logger',
                    'logfire.msg': 'MCP server log from my_logger',
                    'data': 'Dice broken! Improvising...',
                    'logfire.json_schema': {'type': 'object', 'properties': {'data': {}}},
                },
            },
            {
                'name': 'MCP request: tools/call random_number',
                'context': {'trace_id': 2, 'span_id': 15, 'is_remote': False},
                'parent': {'trace_id': 2, 'span_id': 13, 'is_remote': False},
                'start_time': 12000000000,
                'end_time': 15000000000,
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
                        'content': [{'type': 'text', 'text': '4', 'annotations': None}],
                        'isError': False,
                    },
                    'logfire.json_schema': {
                        'type': 'object',
                        'properties': {
                            'request': {
                                'type': 'object',
                                'title': 'ClientRequest',
                                'x-python-datatype': 'PydanticModel',
                                'properties': {
                                    'root': {
                                        'type': 'object',
                                        'title': 'CallToolRequest',
                                        'x-python-datatype': 'PydanticModel',
                                        'properties': {
                                            'params': {
                                                'type': 'object',
                                                'title': 'CallToolRequestParams',
                                                'x-python-datatype': 'PydanticModel',
                                            }
                                        },
                                    }
                                },
                            },
                            'rpc.system': {},
                            'rpc.jsonrpc.version': {},
                            'rpc.method': {},
                            'response': {
                                'type': 'object',
                                'title': 'CallToolResult',
                                'x-python-datatype': 'PydanticModel',
                                'properties': {
                                    'content': {
                                        'type': 'array',
                                        'items': {
                                            'type': 'object',
                                            'title': 'TextContent',
                                            'x-python-datatype': 'PydanticModel',
                                        },
                                    }
                                },
                            },
                        },
                    },
                },
            },
            {
                'name': 'Function: {name}',
                'context': {'trace_id': 2, 'span_id': 13, 'is_remote': False},
                'parent': {'trace_id': 2, 'span_id': 5, 'is_remote': False},
                'start_time': 11000000000,
                'end_time': 16000000000,
                'attributes': {
                    'logfire.msg_template': 'Function: {name}',
                    'logfire.span_type': 'span',
                    'name': 'random_number',
                    'input': {},
                    'output': {'type': 'text', 'text': '4', 'annotations': None},
                    'mcp_data': {'server': 'MyMCPServer'},
                    'gen_ai.system': 'openai',
                    'logfire.msg': 'Function: random_number',
                    'logfire.json_schema': {
                        'type': 'object',
                        'properties': {
                            'name': {},
                            'input': {},
                            'output': {},
                            'mcp_data': {'type': 'object'},
                            'gen_ai.system': {},
                        },
                    },
                },
            },
            {
                'name': 'Responses API with {gen_ai.request.model!r}',
                'context': {'trace_id': 2, 'span_id': 19, 'is_remote': False},
                'parent': {'trace_id': 2, 'span_id': 5, 'is_remote': False},
                'start_time': 17000000000,
                'end_time': 18000000000,
                'attributes': {
                    'code.filepath': 'test_openai_agents_mcp.py',
                    'code.function': 'test_mcp',
                    'code.lineno': 123,
                    'model_settings': {
                        'temperature': None,
                        'top_p': None,
                        'frequency_penalty': None,
                        'presence_penalty': None,
                        'tool_choice': None,
                        'parallel_tool_calls': None,
                        'truncation': None,
                        'max_tokens': None,
                        'reasoning': None,
                        'metadata': None,
                        'store': None,
                        'include_usage': None,
                        'extra_query': None,
                        'extra_body': None,
                        'extra_headers': None,
                    },
                    'gen_ai.request.model': 'gpt-4o',
                    'logfire.msg_template': 'Responses API with {gen_ai.request.model!r}',
                    'logfire.span_type': 'span',
                    'response_id': 'resp_67e6908542b08191a02609780bb4c28205b6a918ffc4827a',
                    'gen_ai.system': 'openai',
                    'gen_ai.response.model': 'gpt-4o-2024-08-06',
                    'response': {
                        'id': 'resp_67e6908542b08191a02609780bb4c28205b6a918ffc4827a',
                        'created_at': 1743163525.0,
                        'error': None,
                        'incomplete_details': None,
                        'instructions': None,
                        'metadata': {},
                        'model': 'gpt-4o-2024-08-06',
                        'object': 'response',
                        'output': [
                            {
                                'id': 'msg_67e69085a34481918093145c9474e87b05b6a918ffc4827a',
                                'content': [
                                    {
                                        'annotations': [],
                                        'text': "Here's a random number for you: 4",
                                        'type': 'output_text',
                                    }
                                ],
                                'role': 'assistant',
                                'status': 'completed',
                                'type': 'message',
                            }
                        ],
                        'parallel_tool_calls': False,
                        'temperature': 1.0,
                        'tool_choice': 'auto',
                        'tools': [
                            {
                                'name': 'random_number',
                                'parameters': {'properties': {}, 'title': 'random_numberArguments', 'type': 'object'},
                                'strict': False,
                                'type': 'function',
                                'description': None,
                            }
                        ],
                        'top_p': 1.0,
                        'background': None,
                        'max_output_tokens': None,
                        'previous_response_id': None,
                        'reasoning': {'effort': None, 'generate_summary': None, 'summary': None},
                        'service_tier': None,
                        'status': 'completed',
                        'text': {'format': {'type': 'text'}},
                        'truncation': 'disabled',
                        'usage': {
                            'input_tokens': 83,
                            'input_tokens_details': {'cached_tokens': 0},
                            'output_tokens': 11,
                            'output_tokens_details': {'reasoning_tokens': 0},
                            'total_tokens': 94,
                        },
                        'user': None,
                        'store': True,
                    },
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
                            'output': '{"type":"text","text":"4","annotations":null}',
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
                            'content': '{"type":"text","text":"4","annotations":null}',
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
                    'logfire.json_schema': {
                        'type': 'object',
                        'properties': {
                            'response_id': {},
                            'gen_ai.system': {},
                            'model_settings': {
                                'type': 'object',
                                'title': 'ModelSettings',
                                'x-python-datatype': 'dataclass',
                            },
                            'gen_ai.request.model': {},
                            'gen_ai.response.model': {},
                            'response': {
                                'type': 'object',
                                'title': 'Response',
                                'x-python-datatype': 'PydanticModel',
                                'properties': {
                                    'output': {
                                        'type': 'array',
                                        'items': {
                                            'type': 'object',
                                            'title': 'ResponseOutputMessage',
                                            'x-python-datatype': 'PydanticModel',
                                            'properties': {
                                                'content': {
                                                    'type': 'array',
                                                    'items': {
                                                        'type': 'object',
                                                        'title': 'ResponseOutputText',
                                                        'x-python-datatype': 'PydanticModel',
                                                    },
                                                }
                                            },
                                        },
                                    },
                                    'tools': {
                                        'type': 'array',
                                        'items': {
                                            'type': 'object',
                                            'title': 'FunctionTool',
                                            'x-python-datatype': 'PydanticModel',
                                        },
                                    },
                                    'reasoning': {
                                        'type': 'object',
                                        'title': 'Reasoning',
                                        'x-python-datatype': 'PydanticModel',
                                    },
                                    'text': {
                                        'type': 'object',
                                        'title': 'ResponseTextConfig',
                                        'x-python-datatype': 'PydanticModel',
                                        'properties': {
                                            'format': {
                                                'type': 'object',
                                                'title': 'ResponseFormatText',
                                                'x-python-datatype': 'PydanticModel',
                                            }
                                        },
                                    },
                                    'usage': {
                                        'type': 'object',
                                        'title': 'ResponseUsage',
                                        'x-python-datatype': 'PydanticModel',
                                        'properties': {
                                            'input_tokens_details': {
                                                'type': 'object',
                                                'title': 'InputTokensDetails',
                                                'x-python-datatype': 'PydanticModel',
                                            },
                                            'output_tokens_details': {
                                                'type': 'object',
                                                'title': 'OutputTokensDetails',
                                                'x-python-datatype': 'PydanticModel',
                                            },
                                        },
                                    },
                                },
                            },
                            'gen_ai.operation.name': {},
                            'raw_input': {'type': 'array'},
                            'events': {'type': 'array'},
                            'gen_ai.usage.input_tokens': {},
                            'gen_ai.usage.output_tokens': {},
                        },
                    },
                },
            },
            {
                'name': 'Agent run: {name!r}',
                'context': {'trace_id': 2, 'span_id': 5, 'is_remote': False},
                'parent': {'trace_id': 2, 'span_id': 3, 'is_remote': False},
                'start_time': 4000000000,
                'end_time': 19000000000,
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
                    'logfire.json_schema': {
                        'type': 'object',
                        'properties': {
                            'name': {},
                            'handoffs': {'type': 'array'},
                            'tools': {'type': 'array'},
                            'output_type': {},
                            'gen_ai.system': {},
                        },
                    },
                },
            },
            {
                'name': 'OpenAI Agents trace: {name}',
                'context': {'trace_id': 2, 'span_id': 3, 'is_remote': False},
                'parent': None,
                'start_time': 3000000000,
                'end_time': 20000000000,
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
                    'logfire.json_schema': {
                        'type': 'object',
                        'properties': {
                            'name': {},
                            'agent_trace_id': {},
                            'group_id': {'type': 'null'},
                            'metadata': {'type': 'null'},
                        },
                    },
                },
            },
        ]
    )
