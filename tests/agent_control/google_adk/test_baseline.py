"""What the adapter tells Logfire the agent already does, which is what the editor offers overrides from."""

from __future__ import annotations

import json
from typing import Any

import pytest
from google.adk.agents.llm_agent import LlmAgent
from google.adk.agents.readonly_context import ReadonlyContext
from google.adk.planners.built_in_planner import BuiltInPlanner
from google.adk.tools.base_tool import BaseTool
from google.adk.tools.base_toolset import BaseToolset
from google.genai import types
from inline_snapshot import snapshot

from logfire.agent_control.google_adk import agent_control
from logfire.variables.local import LocalVariableProvider

from .conftest import baseline, fake_llm, run

pytestmark = pytest.mark.anyio


def get_weather(city: str) -> str:
    """Get the current weather for a city."""
    return f'sunny in {city}'


class DescribedTool(BaseTool):
    """A tool that builds its own declaration, the way an MCP or OpenAPI tool does.

    ADK's `FunctionTool` derives a schema from type hints alone and never reads a docstring's
    `Args:` section, so a plain Python tool has no parameter descriptions to describe. A tool that
    brings its own is what shows the baseline carrying them.
    """

    def __init__(self, name: str = 'search') -> None:
        super().__init__(  # pyright: ignore[reportUnknownMemberType]
            name=name, description='Search CRM records.'
        )

    def _get_declaration(self) -> types.FunctionDeclaration:
        return types.FunctionDeclaration(
            name=self.name,
            description=self.description,
            parameters_json_schema={
                'type': 'object',
                'properties': {'query': {'type': 'string', 'description': 'What to look for.'}},
                'required': ['query'],
            },
        )


class CrmToolset(BaseToolset):
    """One group of tools, which is what the baseline's `toolset` label names."""

    def __init__(self, tool_name: str = 'search', **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.tool_name = tool_name

    async def get_tools(self, readonly_context: ReadonlyContext | None = None) -> list[BaseTool]:
        return [DescribedTool(self.tool_name)]

    async def close(self) -> None:
        return None


async def test_the_baseline_describes_the_agent_as_written(project: LocalVariableProvider) -> None:
    agent = agent_control(
        LlmAgent(
            name='checkout',
            description='Handles refunds.',
            model=fake_llm('gemini-2.5-flash'),
            global_instruction='Escalate anything over $500 to a human.',
            instruction='You are a concise checkout assistant.',
            generate_content_config=types.GenerateContentConfig(
                temperature=0.1,
                max_output_tokens=2048,
                http_options=types.HttpOptions(timeout=5000),
                thinking_config=types.ThinkingConfig(thinking_level=types.ThinkingLevel.LOW),
            ),
            tools=[get_weather, CrmToolset(tool_name_prefix='crm')],
        ),
        label='production',
    )
    await run(agent)
    example = await baseline(project)
    assert example is not None
    assert json.loads(example) == snapshot(
        {
            'instructions': [
                {'id': 'global', 'instructions': 'Escalate anything over $500 to a human.', 'dynamic': False},
                {'id': 'agent', 'instructions': 'You are a concise checkout assistant.', 'dynamic': False},
                {
                    'id': 'identity',
                    'instructions': 'You are an agent. Your internal name is "checkout". The description about you is "Handles refunds.".',
                    'dynamic': False,
                },
            ],
            'model': 'google:gemini-2.5-flash',
            'settings': {'max_tokens': 2048, 'temperature': 0.1, 'timeout': 5.0, 'thinking': 'low'},
            'tool_definitions': [
                {
                    'name': 'get_weather',
                    'description': 'Get the current weather for a city.',
                    'parameters': {'city': {}},
                },
                {
                    'name': 'crm_search',
                    'description': 'Search CRM records.',
                    'parameters': {'query': {'description': 'What to look for.'}},
                    'toolset': 'crm',
                },
            ],
        }
    )


async def test_a_prompt_the_adapter_cannot_reproduce_is_described_but_not_offered(
    project: LocalVariableProvider,
) -> None:
    """A callable prompt and a `{state}` template are both shown as blocks nobody may replace.

    Neither carries text into the baseline. A callable's is not knowable at all, and a template's is
    one request's rendering, built from session state -- and a baseline is published where every
    member of the Logfire project can read it.
    """

    def instruction(context: ReadonlyContext) -> str:
        return 'You are whatever this run needs.'

    agent = agent_control(
        LlmAgent(
            name='checkout',
            model=fake_llm(),
            global_instruction='Serving {tenant}.',
            instruction=instruction,
        ),
        label='production',
    )
    await run(agent, state={'tenant': 'acme'})
    example = await baseline(project)
    assert example is not None
    assert json.loads(example) == snapshot(
        {
            'instructions': [
                {'id': 'global', 'dynamic': True},
                {'id': 'agent', 'dynamic': True},
                {
                    'id': 'identity',
                    'instructions': 'You are an agent. Your internal name is "checkout".',
                    'dynamic': False,
                },
            ],
            'model': 'fake-code-model',
        }
    )


async def test_two_toolsets_of_one_class_are_not_shown_as_one_group(project: LocalVariableProvider) -> None:
    """A group label only means something if an override written against it addresses one group.

    A class name does not: two `MCPToolset`s side by side would be shown as one, and an override
    narrowed to that label would patch a tool in the other. Ungrouped is what they get instead, and
    naming either of them with a `tool_name_prefix` is what gets the grouping back.
    """
    agent = agent_control(
        LlmAgent(
            name='checkout',
            model=fake_llm(),
            tools=[CrmToolset('search'), CrmToolset('lookup'), CrmToolset('escalate', tool_name_prefix='support')],
        ),
        label='production',
    )
    await run(agent)
    example = await baseline(project)
    assert example is not None
    published: dict[str, Any] = json.loads(example)
    assert [(tool['name'], tool.get('toolset')) for tool in published['tool_definitions']] == snapshot(
        [('search', None), ('lookup', None), ('support_escalate', 'support')]
    )


async def test_the_baseline_describes_the_thinking_the_planner_actually_does(
    project: LocalVariableProvider,
) -> None:
    """A `BuiltInPlanner` puts its `thinking_config` on every request, so it is what the agent does.

    ADK itself warns when an agent sets one in both places, so the planner is the *only* place this
    agent's thinking is written -- and reading only `generate_content_config` would describe an agent
    that does not think at all.
    """
    agent = agent_control(
        LlmAgent(
            name='checkout',
            model=fake_llm(),
            generate_content_config=types.GenerateContentConfig(temperature=0.1),
            planner=BuiltInPlanner(thinking_config=types.ThinkingConfig(thinking_budget=0)),
        ),
        label='production',
    )
    await run(agent)
    example = await baseline(project)
    assert example is not None
    published: dict[str, Any] = json.loads(example)
    assert published['settings'] == snapshot({'temperature': 0.1, 'thinking': False})


async def test_the_baseline_says_it_was_taken_from_a_request(project: LocalVariableProvider) -> None:
    """Which is what it is: the tool list and the prompt's seams are one request's, not the code's."""
    agent = agent_control(LlmAgent(name='checkout', model=fake_llm(), instruction='Code.'), label='production')
    await run(agent)
    assert await baseline(project) is not None
    config = project.get_variable_config('agent__checkout')
    assert config is not None
    assert 'snapshotted from one request' in (config.description or '')


async def test_the_baseline_is_published_once(project: LocalVariableProvider) -> None:
    llm = fake_llm(script=['get_weather'])
    agent = agent_control(
        LlmAgent(name='checkout', model=llm, instruction='One.', tools=[get_weather]),
        label='production',
    )
    await run(agent)
    assert len(llm.requests) == 2
    example = await baseline(project)
    assert example is not None
    published: dict[str, Any] = json.loads(example)
    # Both requests went through the hook, and only the first described the agent -- the tool result
    # in the second request's prompt is not a second, different baseline.
    assert [entry['id'] for entry in published['instructions']] == ['agent', 'identity']
