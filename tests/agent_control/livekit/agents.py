"""The agent, tools, and session runner the integration tests share."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from typing import Any

from livekit.agents import Agent, AgentSession, RunContext, llm
from livekit.agents.llm.chat_context import Instructions
from livekit.agents.types import NOT_GIVEN, NotGivenOr
from livekit.agents.voice.run_result import RunResult

from logfire.agent_control import AgentControl, OnUnmatched
from logfire.agent_control.livekit import agent_control

CONTEXTS: list[RunContext[Any]] = []
"""Every `RunContext` a tool call was handed, so a test can dispatch a tool with a real one."""


@llm.function_tool
async def get_weather(ctx: RunContext[Any], city: str) -> str:
    """Get the current weather for a city.

    Args:
        city: The city to look up.
    """
    CONTEXTS.append(ctx)
    return f'weather({ctx.function_call.name}, {city})'


@llm.function_tool
async def convert_currency(amount: float, to: str) -> str:
    """Convert an amount to another currency.

    Args:
        amount: The amount to convert.
        to: The currency to convert to.
    """
    return f'{amount} {to}'


@llm.function_tool(
    raw_schema={
        'name': 'lookup_order',
        'description': 'Look up an order.',
        'parameters': {'type': 'object', 'properties': {'order_id': {'type': 'string', 'description': 'Order id.'}}},
    }
)
async def lookup_order(raw_arguments: dict[str, Any]) -> str:
    return 'shipped'


@llm.function_tool(raw_schema={'name': 'ping', 'parameters': {'type': 'object', 'properties': {}}})
async def ping(raw_arguments: dict[str, Any]) -> str:
    """A raw-schema tool whose schema carries no description at all."""
    return 'pong'


class ProviderSearch(llm.ProviderTool):
    """A tool the provider runs itself, which has no model-facing definition of ours to edit."""

    def __init__(self) -> None:
        super().__init__(id='provider_search')


def managed(
    name: str = 'checkout',
    *,
    label: str | None = 'production',
    instructions: str | Instructions = 'CODE',
    tools: Sequence[llm.Tool | llm.Toolset] = (),
    model: NotGivenOr[llm.LLM | llm.RealtimeModel] = NOT_GIVEN,
    on_unmatched: OnUnmatched = 'warn',
    publish_baseline: bool = True,
) -> Callable[[], Agent]:
    """A managed agent class, as a factory: `Agent.__init__` needs arguments this one supplies."""

    @agent_control(name=name, label=label, on_unmatched=on_unmatched, publish_baseline=publish_baseline)
    class ExampleAgent(Agent):
        def __init__(self) -> None:
            super().__init__(instructions=instructions, tools=list(tools), llm=model)

    return ExampleAgent


def control_of(agent_cls: object) -> AgentControl:
    """The control a managed class was bound to, for a test that waits on its baseline publish."""
    control = getattr(agent_cls, '_agent_control')
    assert isinstance(control, AgentControl)
    return control


async def run(agent: Agent, model: llm.LLM, user_input: str = 'Weather in Paris?') -> RunResult:
    """Drive one turn against a stub model, the way LiveKit's own offline test harness does."""
    session = AgentSession(llm=model)
    await session.start(agent)
    try:
        return await session.run(user_input=user_input)
    finally:
        await session.aclose()


def names(tools: Iterable[llm.Tool | llm.Toolset]) -> list[str]:
    """The model-facing names of the function tools in a list, in order."""
    return [tool.info.name for tool in tools if isinstance(tool, (llm.FunctionTool, llm.RawFunctionTool))]


def outputs(result: RunResult) -> list[tuple[str, str]]:
    """The tool results of a run, as (name, output) under the names the code saw."""
    return [
        (item.name, item.output)
        for item in (event.item for event in result.events)
        if item.type == 'function_call_output'
    ]
