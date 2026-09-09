"""One example agent, built the way a user would, reused across the tests."""

from __future__ import annotations

from typing import Annotated, Any

from claude_agent_sdk import AgentDefinition, ClaudeAgentOptions, SdkMcpTool, tool

from logfire.agent_control.claude_agent_sdk import sdk_mcp_server


@tool('refund_order', 'Refund an order.', {'order_id': Annotated[str, 'The order to refund.']})
async def refund_order(args: dict[str, Any]) -> dict[str, Any]:
    return {'content': [{'type': 'text', 'text': f'refunded {args["order_id"]}'}]}


@tool('search', 'Search the catalogue.', {'query': str})
async def search(args: dict[str, Any]) -> dict[str, Any]:
    return {'content': [{'type': 'text', 'text': f'found {args["query"]}'}]}


def checkout_options(**overrides: Any) -> ClaudeAgentOptions:
    """The agent every test starts from: a custom prompt, a subagent, and two in-process tools."""
    tools: list[SdkMcpTool[Any]] = [refund_order, search]
    defaults: dict[str, Any] = dict(
        system_prompt='You are a concise checkout assistant.',
        model='claude-fable-5-1',
        effort='high',
        agents={'reviewer': AgentDefinition(description='Reviews refunds.', prompt='You review refunds.')},
        mcp_servers={'shop': sdk_mcp_server('shop', tools=tools)},
        allowed_tools=['mcp__shop__refund_order', 'Read(*.py)'],
    )
    defaults.update(overrides)
    return ClaudeAgentOptions(**defaults)
