"""Renaming and redescribing tools for the model, without moving what the code does."""
# pyright: reportPrivateUsage=false

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from typing import Any

import pytest
from google.adk.agents.llm_agent import LlmAgent
from google.adk.agents.readonly_context import ReadonlyContext
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.adk.tools.base_tool import BaseTool
from google.adk.tools.base_toolset import BaseToolset
from google.adk.tools.tool_context import ToolContext
from google.genai import types
from google.genai.types import Type
from inline_snapshot import snapshot

from logfire.agent_control.google_adk import agent_control
from logfire.variables.local import LocalVariableProvider

from .conftest import Conversation, FakeLlm, declarations, fake_llm, publish, republish, run

pytestmark = pytest.mark.anyio

CALLS: list[tuple[str, dict[str, Any]]] = []


@pytest.fixture(autouse=True)
def _forget_calls() -> None:  # pyright: ignore[reportUnusedFunction]
    CALLS.clear()


def get_weather(city: str) -> str:
    """Get the current weather for a city."""
    CALLS.append(('get_weather', {'city': city}))
    return f'sunny in {city}'


def lookup_weather(city: str) -> str:
    """Another tool that already answers to the name an override might want."""
    CALLS.append(('lookup_weather', {'city': city}))  # pragma: no cover - only its name matters here
    return 'unused'  # pragma: no cover


class SchemaTool(BaseTool):
    """A tool declaring its parameters as a genai `Schema`, which is ADK's older shape."""

    def __init__(self) -> None:
        super().__init__(  # pyright: ignore[reportUnknownMemberType]
            name='search', description='Search CRM records.'
        )

    def _get_declaration(self) -> types.FunctionDeclaration:
        return types.FunctionDeclaration(
            name=self.name,
            description=self.description,
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    'query': types.Schema(type=types.Type.STRING, description='What to look for.'),
                    # No description in code, and none published: it stays as the tool declared it.
                    'limit': types.Schema(type=types.Type.INTEGER),
                },
            ),
        )

    async def run_async(self, *, args: dict[str, Any], tool_context: ToolContext) -> Any:
        CALLS.append((self.name, args))
        return 'nothing found'


class CrmToolset(BaseToolset):
    """A toolset, which is the grouping a `toolset`-qualified override narrows to."""

    def __init__(self, *, fail_after: int | None = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.listings = 0
        self.fail_after = fail_after

    async def get_tools(self, readonly_context: ReadonlyContext | None = None) -> list[BaseTool]:
        self.listings += 1
        if self.fail_after is not None and self.listings > self.fail_after:
            raise RuntimeError('the CRM is down')
        return [SchemaTool()]

    async def close(self) -> None:
        return None


async def test_a_managed_definition_is_what_the_model_is_shown(project: LocalVariableProvider) -> None:
    publish(
        project,
        {
            'tool_definitions': [
                {
                    'name': 'get_weather',
                    'new_name': 'lookup_weather',
                    'description': 'Look up the current weather for a city.',
                    'parameters': {'city': {'description': "City name, e.g. 'London'"}},
                }
            ]
        },
    )
    llm = fake_llm(script=['lookup_weather'])
    agent = agent_control(LlmAgent(name='checkout', model=llm, tools=[get_weather]), label='production')
    await run(agent)

    declaration = declarations(llm.requests[0])[0]
    assert (declaration.name, declaration.description) == snapshot(
        ('lookup_weather', 'Look up the current weather for a city.')
    )
    assert declaration.parameters_json_schema == snapshot(
        {
            'properties': {'city': {'title': 'City', 'type': 'string', 'description': "City name, e.g. 'London'"}},
            'required': ['city'],
            'title': 'get_weatherParams',
            'type': 'object',
        }
    )
    # The model called the managed name, and the code tool ran with the arguments it defines.
    assert CALLS == snapshot([('get_weather', {'city': 'Paris'})])


def replayed(llm: FakeLlm, index: int) -> list[str]:
    """Every tool name the conversation replayed to the model on one request."""
    return [
        (part.function_call or part.function_response).name or ''  # pyright: ignore[reportOptionalMemberAccess]
        for content in llm.requests[index].contents
        for part in content.parts or []
        if part.function_call or part.function_response
    ]


async def test_your_code_sees_the_name_your_code_gave_the_tool(project: LocalVariableProvider) -> None:
    """A rename is what the model is told and nothing else: it stops at the model boundary."""
    publish(project, {'tool_definitions': [{'name': 'get_weather', 'new_name': 'lookup_weather'}]})
    seen: list[str] = []
    llm = fake_llm(script=['lookup_weather'])
    conversation = Conversation(
        agent_control(
            LlmAgent(
                name='checkout',
                model=llm,
                tools=[get_weather],
                before_tool_callback=lambda tool, args, tool_context: seen.append(tool.name),
            ),
            label='production',
        )
    )
    try:
        await conversation.turn()
        # The model was shown the managed name and called it; the code tool ran under the name the
        # code gave it, in the callback that guards it and in the events the session persists.
        assert declarations(llm.requests[0])[0].name == snapshot('lookup_weather')
        assert seen == snapshot(['get_weather'])
        assert CALLS == snapshot([('get_weather', {'city': 'Paris'})])
        assert await conversation.tool_names() == snapshot(['get_weather', 'get_weather'])
    finally:
        await conversation.close()
    # And the model still sees one consistent transcript: the persisted code names are translated
    # forward into what this request advertises.
    assert replayed(llm, 1) == snapshot(['lookup_weather', 'lookup_weather'])


async def test_a_rename_that_changes_mid_conversation_still_reads_as_one_transcript(
    project: LocalVariableProvider,
) -> None:
    """History is kept in the code's names, so what the model is shown is whatever is published now."""
    publish(project, {'tool_definitions': [{'name': 'get_weather', 'new_name': 'lookup_weather'}]})
    llm = fake_llm(script=['lookup_weather', None, 'fetch_weather', None])
    conversation = Conversation(
        agent_control(LlmAgent(name='checkout', model=llm, tools=[get_weather]), label='production')
    )
    try:
        await conversation.turn()
        republish(project, {'tool_definitions': [{'name': 'get_weather', 'new_name': 'fetch_weather'}]})
        await conversation.turn()
        # Both turns dispatched, and the session holds one name for all of it.
        assert CALLS == snapshot([('get_weather', {'city': 'Paris'}), ('get_weather', {'city': 'Paris'})])
        assert await conversation.tool_names() == snapshot(['get_weather', 'get_weather', 'get_weather', 'get_weather'])
    finally:
        await conversation.close()
    # The turn taken under the old rename is replayed under the new one, so nothing the model is
    # shown names a tool it was not offered.
    assert replayed(llm, 2) == snapshot(['fetch_weather', 'fetch_weather'])


async def test_a_rename_withdrawn_mid_conversation_leaves_nothing_behind(
    project: LocalVariableProvider,
) -> None:
    """Removing the override in Logfire puts the code's name back, in the tool list and the history."""
    publish(project, {'tool_definitions': [{'name': 'get_weather', 'new_name': 'lookup_weather'}]})
    llm = fake_llm(script=['lookup_weather', None, 'get_weather', None])
    conversation = Conversation(
        agent_control(LlmAgent(name='checkout', model=llm, tools=[get_weather]), label='production')
    )
    try:
        await conversation.turn()
        republish(project, {})
        await conversation.turn()
        assert CALLS == snapshot([('get_weather', {'city': 'Paris'}), ('get_weather', {'city': 'Paris'})])
    finally:
        await conversation.close()
    assert [d.name for d in declarations(llm.requests[2])] == snapshot(['get_weather'])
    assert replayed(llm, 2) == snapshot(['get_weather', 'get_weather'])


async def test_a_forced_tool_choice_names_the_tool_the_model_was_shown(project: LocalVariableProvider) -> None:
    """`allowed_function_names` is the code's own choice of tools, and it has to survive the overlay."""
    publish(project, {'tool_definitions': [{'name': 'get_weather', 'new_name': 'lookup_weather'}]})
    llm = fake_llm(script=['lookup_weather'])
    tool_config = types.ToolConfig(
        function_calling_config=types.FunctionCallingConfig(
            mode=types.FunctionCallingConfigMode.ANY, allowed_function_names=['get_weather']
        )
    )
    agent = agent_control(
        LlmAgent(
            name='checkout',
            model=llm,
            tools=[get_weather],
            generate_content_config=types.GenerateContentConfig(tool_config=tool_config),
        ),
        label='production',
    )
    await run(agent)
    sent = llm.requests[0].config.tool_config
    assert sent is not None and sent.function_calling_config is not None
    assert sent.function_calling_config.allowed_function_names == snapshot(['lookup_weather'])
    # Rewritten onto a copy: the agent's own object is shared with every run it will ever make.
    assert tool_config.function_calling_config is not None
    assert tool_config.function_calling_config.allowed_function_names == snapshot(['get_weather'])


async def test_a_forced_tool_choice_naming_no_renamed_tool_is_left_as_it_is(
    project: LocalVariableProvider,
) -> None:
    """A rename somewhere else in the tool list is no reason to rebuild the agent's own selection."""
    publish(project, {'tool_definitions': [{'name': 'get_weather', 'new_name': 'look_up_weather'}]})
    llm = fake_llm(script=['lookup_weather'])
    tool_config = types.ToolConfig(
        function_calling_config=types.FunctionCallingConfig(allowed_function_names=['lookup_weather'])
    )
    agent = agent_control(
        LlmAgent(
            name='checkout',
            model=llm,
            tools=[get_weather, lookup_weather],
            generate_content_config=types.GenerateContentConfig(tool_config=tool_config),
        ),
        label='production',
    )
    await run(agent)
    assert llm.requests[0].config.tool_config is tool_config


async def test_two_interleaved_runs_each_dispatch_their_own_rename(project: LocalVariableProvider) -> None:
    """Routing belongs to the request that resolved it, not to the agent the two runs share."""
    publish(project, {'tool_definitions': [{'name': 'get_weather', 'new_name': 'lookup_weather'}]})
    first_sent = asyncio.Event()
    second_done = asyncio.Event()

    class InterleavingLlm(FakeLlm):
        """Calls whatever it was advertised, holding the first request open until the second is done."""

        async def generate_content_async(
            self, llm_request: LlmRequest, stream: bool = False
        ) -> AsyncGenerator[LlmResponse, None]:
            self.requests.append(llm_request)
            if not first_sent.is_set():
                first_sent.set()
                await second_done.wait()
            answered = any(part.function_response for content in llm_request.contents for part in content.parts or [])
            part = (
                types.Part.from_text(text='done')
                if answered
                else types.Part.from_function_call(name=declarations(llm_request)[0].name or '', args={'city': 'Paris'})
            )
            yield LlmResponse(content=types.Content(role='model', parts=[part]))

    agent = agent_control(
        LlmAgent(name='checkout', model=InterleavingLlm(model='fake-code-model', requests=[]), tools=[get_weather]),
        label='production',
    )
    first, second = Conversation(agent), Conversation(agent)
    try:
        held = asyncio.ensure_future(first.turn())
        await first_sent.wait()
        # The rename changes while the first run is waiting on its model, so at one moment the two
        # runs are holding different routings for the same agent.
        republish(project, {'tool_definitions': [{'name': 'get_weather', 'new_name': 'fetch_weather'}]})
        await second.turn()
        second_done.set()
        await held
        # Each run's call came back under the name that run advertised, and both reached the code.
        assert CALLS == snapshot([('get_weather', {'city': 'Paris'}), ('get_weather', {'city': 'Paris'})])
        assert await first.tool_names() == snapshot(['get_weather', 'get_weather'])
        assert await second.tool_names() == snapshot(['get_weather', 'get_weather'])
    finally:
        await first.close()
        await second.close()


async def test_the_agents_own_tool_keeps_the_name_code_gave_it(project: LocalVariableProvider) -> None:
    """The rename is one request's, so removing it in Logfire really does put the old name back."""
    publish(project, {'tool_definitions': [{'name': 'get_weather', 'new_name': 'lookup_weather'}]})
    agent = agent_control(LlmAgent(name='checkout', model=fake_llm(), tools=[get_weather]), label='production')
    await run(agent)
    assert [tool.name for tool in await agent.canonical_tools()] == snapshot(['get_weather'])


async def test_a_rename_onto_a_name_already_taken_is_dropped(project: LocalVariableProvider) -> None:
    publish(
        project,
        {'tool_definitions': [{'name': 'get_weather', 'new_name': 'lookup_weather', 'description': 'Managed.'}]},
    )
    llm = fake_llm()
    agent = agent_control(LlmAgent(name='checkout', model=llm, tools=[get_weather, lookup_weather]), label='production')
    with pytest.warns(UserWarning, match='which is already advertised by another tool'):
        await run(agent)
    # The rename went, the description stayed, and both tools still have a name the model can call.
    assert [(d.name, d.description) for d in declarations(llm.requests[0])] == snapshot(
        [
            ('get_weather', 'Managed.'),
            ('lookup_weather', 'Another tool that already answers to the name an override might want.'),
        ]
    )


async def test_parameters_declared_the_older_way_are_patched_too(project: LocalVariableProvider) -> None:
    publish(
        project,
        {'tool_definitions': [{'name': 'crm_search', 'parameters': {'query': {'description': 'Managed.'}}}]},
    )
    llm = fake_llm()
    agent = agent_control(
        LlmAgent(name='checkout', model=llm, tools=[CrmToolset(tool_name_prefix='crm')]), label='production'
    )
    await run(agent)
    declaration = declarations(llm.requests[0])[0]
    assert declaration.parameters is not None
    assert declaration.parameters.model_dump(exclude_none=True) == snapshot(
        {
            'properties': {'query': {'description': 'Managed.', 'type': Type.STRING}, 'limit': {'type': Type.INTEGER}},
            'type': Type.OBJECT,
        }
    )


async def test_an_override_can_be_narrowed_to_one_toolset(project: LocalVariableProvider) -> None:
    publish(
        project,
        {
            'tool_definitions': [
                {'name': 'crm_search', 'toolset': 'crm', 'description': 'The CRM search.'},
                {'name': 'crm_search', 'toolset': 'billing', 'description': 'Some other search.'},
            ]
        },
    )
    llm = fake_llm()
    agent = agent_control(
        LlmAgent(name='checkout', model=llm, tools=[CrmToolset(tool_name_prefix='crm')]), label='production'
    )
    with pytest.warns(UserWarning, match="patches tool 'crm_search' from toolset 'billing'"):
        await run(agent)
    assert declarations(llm.requests[0])[0].description == snapshot('The CRM search.')


async def test_a_toolset_that_cannot_list_itself_costs_only_its_label(project: LocalVariableProvider) -> None:
    """Grouping is for the editor; a request the agent is otherwise ready to make still goes out."""
    publish(project, {'tool_definitions': [{'name': 'crm_search', 'description': 'Managed.'}]})
    llm = fake_llm()
    toolset = CrmToolset(tool_name_prefix='crm', fail_after=1)
    toolset._use_invocation_cache = False
    agent = agent_control(LlmAgent(name='checkout', model=llm, tools=[toolset]), label='production')
    await run(agent)
    assert declarations(llm.requests[0])[0].description == snapshot('Managed.')


async def test_a_tool_this_agent_does_not_advertise_is_reported(project: LocalVariableProvider) -> None:
    publish(project, {'tool_definitions': [{'name': 'refund', 'description': 'Managed.'}]})
    agent = agent_control(LlmAgent(name='checkout', model=fake_llm(), tools=[get_weather]), label='production')
    with pytest.warns(UserWarning, match="patches tool 'refund', which no toolset advertises"):
        await run(agent)


async def test_a_provider_side_tool_has_no_definition_to_manage(project: LocalVariableProvider) -> None:
    """Google Search and friends are not tools the model is shown a patchable declaration for."""
    publish(project, {'tool_definitions': [{'name': 'get_weather', 'description': 'Managed.'}]})
    llm = fake_llm()
    agent = agent_control(LlmAgent(name='checkout', model=llm, tools=[get_weather]), label='production')
    agent.before_model_callback = [
        lambda callback_context, llm_request: (llm_request.config.tools or []).append(
            types.Tool(google_search=types.GoogleSearch())
        ),
        *agent.canonical_before_model_callbacks,
    ]
    await run(agent)
    assert [d.name for d in declarations(llm.requests[0])] == snapshot(['get_weather'])
    assert declarations(llm.requests[0])[0].description == snapshot('Managed.')


class NoArgumentTool(BaseTool):
    """A tool the model calls with nothing, so there is no parameter schema to describe or patch."""

    def __init__(self) -> None:
        super().__init__(  # pyright: ignore[reportUnknownMemberType]
            name='escalate', description='Hand the conversation to a human.'
        )

    def _get_declaration(self) -> types.FunctionDeclaration:
        return types.FunctionDeclaration(name=self.name, description=self.description)

    async def run_async(self, *, args: dict[str, Any], tool_context: ToolContext) -> Any:
        CALLS.append((self.name, args))  # pragma: no cover - the model never calls it here
        return 'escalated'  # pragma: no cover


async def test_a_tool_with_no_parameters_is_managed_like_any_other(project: LocalVariableProvider) -> None:
    publish(project, {'tool_definitions': [{'name': 'escalate', 'description': 'Managed.'}]})
    llm = fake_llm()
    agent = agent_control(LlmAgent(name='checkout', model=llm, tools=[NoArgumentTool()]), label='production')
    await run(agent)
    declaration = declarations(llm.requests[0])[0]
    assert (declaration.description, declaration.parameters, declaration.parameters_json_schema) == snapshot(
        ('Managed.', None, None)
    )


async def test_a_declaration_nothing_dispatches_is_still_renamed_for_the_model(
    project: LocalVariableProvider,
) -> None:
    """A plugin can put a declaration on the request that no tool in `tools_dict` answers to."""
    publish(project, {'tool_definitions': [{'name': 'ghost', 'new_name': 'phantom'}]})
    llm = fake_llm()
    agent = agent_control(LlmAgent(name='checkout', model=llm, tools=[get_weather]), label='production')

    def inject(callback_context: Any, llm_request: Any) -> None:
        llm_request.config.tools = [
            # Not a `types.Tool` at all: genai also accepts a plain dictionary in this list.
            {'google_search': {}},
            *(llm_request.config.tools or []),
            types.Tool(function_declarations=[types.FunctionDeclaration(name='ghost')]),
        ]

    agent.before_model_callback = [inject, *agent.canonical_before_model_callbacks]
    await run(agent)
    assert [d.name for d in declarations(llm.requests[0])] == snapshot(['get_weather', 'phantom'])
    assert sorted(llm.requests[0].tools_dict) == snapshot(['get_weather'])


async def test_a_parameter_the_older_shape_never_described_is_left_undescribed(
    project: LocalVariableProvider,
) -> None:
    publish(project, {'tool_definitions': [{'name': 'crm_search', 'parameters': {'query': {'description': 'M.'}}}]})
    llm = fake_llm(script=['crm_search'])
    agent = agent_control(
        LlmAgent(name='checkout', model=llm, tools=[CrmToolset(tool_name_prefix='crm')]), label='production'
    )
    await run(agent)
    declaration = declarations(llm.requests[0])[0]
    assert declaration.parameters is not None
    assert declaration.parameters.model_dump(exclude_none=True, mode='json') == snapshot(
        {
            'properties': {'query': {'description': 'M.', 'type': 'STRING'}, 'limit': {'type': 'INTEGER'}},
            'type': 'OBJECT',
        }
    )
    # And the tool the toolset owns ran, under the name the model was shown.
    assert CALLS == snapshot([('crm_search', {'city': 'Paris'})])
