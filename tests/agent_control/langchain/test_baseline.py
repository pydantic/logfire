"""What the adapter publishes as the agent-as-it-runs, which is what the Logfire editor opens on."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, cast

import pytest
from inline_snapshot import snapshot
from langchain_core.messages import AIMessage, SystemMessage
from langchain_core.messages.content import create_text_block
from langchain_core.tools import BaseTool, tool

from logfire.agent_control.langchain import agent_control
from logfire.variables.local import LocalVariableProvider

from .conftest import AGENT_VARIABLE, RecordingModel, build_agent, declared_prompt, published_baseline, run, variable


def test_the_baseline_describes_what_the_agent_sends(
    project: LocalVariableProvider, wait_for_publish: Callable[[], None]
) -> None:
    model = RecordingModel(provider='anthropic', model='claude-fable-5-1', temperature=0.1, replies=[AIMessage('ok')])
    middleware = agent_control(label='production')
    run(build_agent(model, middleware, system_prompt=declared_prompt('You are a concise checkout assistant.')))
    wait_for_publish()

    assert published_baseline(project) == snapshot(
        {
            'instructions': [
                {'id': 'system:role', 'instructions': 'You are a concise checkout assistant.', 'dynamic': False}
            ],
            'model': 'anthropic:claude-fable-5-1',
            'settings': {'temperature': 0.1},
            'tool_definitions': [
                {
                    'name': 'get_weather',
                    'description': 'Get the current weather for a city.',
                    'parameters': {'city': {'description': 'The city to look up.'}},
                },
                {
                    'name': 'get_time',
                    'description': 'Get the current time in a city.',
                    'parameters': {'city': {'description': 'The city to look up.'}},
                },
            ],
        }
    )


def test_the_baseline_says_it_was_read_off_a_request(
    project: LocalVariableProvider, wait_for_publish: Callable[[], None]
) -> None:
    # `create_agent` keeps the prompt, the model and the tool list in a closure, so the earliest
    # anything here can be read is a request -- and the model, the settings and the tools in this
    # baseline are the ones *that* request carried, which the variable says rather than implies.
    middleware = agent_control(label='production')
    run(build_agent(RecordingModel(replies=[AIMessage('ok')]), middleware, tools=[]))
    wait_for_publish()

    description = variable(project).description
    assert description is not None and 'snapshotted from one request' in description


def test_text_the_adapter_cannot_attribute_to_the_code_is_published_as_a_seam(
    project: LocalVariableProvider,
    wait_for_publish: Callable[[], None],
) -> None:
    # The blocker this rule exists for: a prompt computed per request carries this tenant's name,
    # this user's id, this run's retrieved documents. It reaches the middleware as an ordinary
    # string, and the baseline goes into a variable every member of the Logfire project can read.
    middleware = agent_control(label='production')
    prompt = 'You are the assistant for ACME Corp. The customer is jane@example.com.'
    run(build_agent(RecordingModel(replies=[AIMessage('ok')]), middleware, tools=[], system_prompt=prompt))
    wait_for_publish()

    assert published_baseline(project)['instructions'] == snapshot([{'id': 'system', 'dynamic': True}])


def test_the_variable_is_created_with_the_shared_schema(
    project: LocalVariableProvider, wait_for_publish: Callable[[], None]
) -> None:
    middleware = agent_control(label='production')
    run(build_agent(RecordingModel(replies=[AIMessage('ok')]), middleware))
    wait_for_publish()

    json_schema = variable(project).json_schema
    assert json_schema is not None and 'instructions' in json_schema['properties']


def test_a_block_id_langchain_generated_is_not_a_declaration(
    project: LocalVariableProvider, wait_for_publish: Callable[[], None]
) -> None:
    # The blocker: `create_text_block()` puts an `lc_<uuid4>` on every block it makes, so a
    # middleware that assembles this request's prompt with LangChain's own helpers hands over text
    # carrying an id. Reading that as the code author's declaration would publish this request's
    # data -- this tenant, this user -- into a variable the whole project can read, and address it
    # by an id no later request will ever carry again.
    # Cast because `create_text_block` returns a `TypedDict` and `SystemMessage.content` is typed
    # as taking plain `dict`s, which a `TypedDict` is not assignable to.
    content = cast(
        'list[str | dict[Any, Any]]',
        [
            create_text_block('You are a checkout assistant.', id='role'),
            create_text_block('The customer is jane@example.com.'),
        ],
    )
    prompt = SystemMessage(content=content)
    middleware = agent_control(label='production')
    run(build_agent(RecordingModel(replies=[AIMessage('ok')]), middleware, tools=[], system_prompt=prompt))
    wait_for_publish()

    assert published_baseline(project)['instructions'] == snapshot(
        [
            {'id': 'system:role', 'instructions': 'You are a checkout assistant.', 'dynamic': False},
            {'id': 'system:1', 'dynamic': True},
        ]
    )


def test_each_block_of_a_structured_prompt_is_its_own_baseline_entry(
    project: LocalVariableProvider, wait_for_publish: Callable[[], None]
) -> None:
    prompt = SystemMessage(
        content=[
            {'type': 'text', 'text': 'You are a checkout assistant.', 'id': 'role'},
            {'type': 'text', 'text': 'Always confirm the order total.'},
        ]
    )
    middleware = agent_control(label='production')
    run(build_agent(RecordingModel(replies=[AIMessage('ok')]), middleware, tools=[], system_prompt=prompt))
    wait_for_publish()

    # The declared block is published with its text; its unlabelled neighbour is a seam, because
    # nothing here can tell a block the code wrote from one a middleware ahead of it produced.
    assert published_baseline(project)['instructions'] == snapshot(
        [
            {'id': 'system:role', 'instructions': 'You are a checkout assistant.', 'dynamic': False},
            {'id': 'system:1', 'dynamic': True},
        ]
    )


def test_an_agent_with_no_prompt_and_no_tools_publishes_neither(
    project: LocalVariableProvider, wait_for_publish: Callable[[], None]
) -> None:
    middleware = agent_control(label='production')
    run(build_agent(RecordingModel(replies=[AIMessage('ok')]), middleware, tools=[], system_prompt=None))
    wait_for_publish()

    assert published_baseline(project) == snapshot({'model': 'openai:fake-1'})


def test_a_model_that_reports_no_identifier_costs_the_baseline_only_its_model(
    project: LocalVariableProvider, wait_for_publish: Callable[[], None]
) -> None:
    class UnidentifiedModel(RecordingModel):
        def _get_ls_params(self, stop: list[str] | None = None, **kwargs: Any) -> Any:
            return {'ls_provider': 'openai', 'ls_model_type': 'chat'}

    middleware = agent_control(label='production')
    run(
        build_agent(UnidentifiedModel(replies=[AIMessage('ok')]), middleware, tools=[], system_prompt=declared_prompt())
    )
    wait_for_publish()

    assert published_baseline(project) == snapshot(
        {'instructions': [{'id': 'system:role', 'instructions': 'You are a helpful assistant.', 'dynamic': False}]}
    )


def test_a_code_setting_the_contract_cannot_hold_is_left_out_and_said_out_loud(
    project: LocalVariableProvider,
    wait_for_publish: Callable[[], None],
) -> None:
    # Anthropic's `reasoning_effort` accepts `'max'`, which the contract's effort levels do not, and
    # the baseline is not the place to teach every reader of the project a value it will drop.
    model = RecordingModel(reasoning_effort='max', temperature=0.2, replies=[AIMessage('ok')])
    middleware = agent_control(label='production')
    agent = build_agent(model, middleware, tools=[])

    with pytest.warns(UserWarning, match="runs with thinking='max', which the Agent Control contract cannot"):
        run(agent)
    wait_for_publish()
    assert published_baseline(project)['settings'] == snapshot({'temperature': 0.2})


def test_the_baseline_is_published_from_the_first_request_only(
    project: LocalVariableProvider, wait_for_publish: Callable[[], None]
) -> None:
    middleware = agent_control(label='production')
    agent = build_agent(RecordingModel(replies=[AIMessage('ok')]), middleware, tools=[])
    run(agent)
    wait_for_publish()
    published = published_baseline(project)

    # A second run happens against the variable the first one created, and writes nothing more.
    project.update_variable(AGENT_VARIABLE, variable(project).model_copy(update={'example': 'edited in the UI'}))
    run(agent)
    wait_for_publish()
    assert variable(project).example == 'edited in the UI'
    assert published['model'] == 'openai:fake-1'


def test_publishing_can_be_turned_off(project: LocalVariableProvider, wait_for_publish: Callable[[], None]) -> None:
    middleware = agent_control(label='production', publish_baseline=False)
    run(build_agent(RecordingModel(replies=[AIMessage('ok')]), middleware, tools=[]))
    wait_for_publish()

    assert project.get_variable_config(AGENT_VARIABLE) is None


def test_a_tool_without_documented_parameters_publishes_empty_entries(
    project: LocalVariableProvider, wait_for_publish: Callable[[], None]
) -> None:
    @tool
    def ping(host: str) -> str:
        """Ping a host."""
        return 'pong'

    middleware = agent_control(label='production')
    run(build_agent(RecordingModel(replies=[AIMessage('ok')]), middleware, tools=[cast_tool(ping)]))
    wait_for_publish()

    assert cast_tool(ping).invoke({'host': 'example.com'}) == 'pong'
    # An undocumented parameter is listed with an empty entry, so the editor can give it its first
    # description without someone documenting it in code first.
    assert published_baseline(project)['tool_definitions'] == snapshot(
        [{'name': 'ping', 'description': 'Ping a host.', 'parameters': {'host': {}}}]
    )


def cast_tool(value: Any) -> BaseTool:
    """`@tool` returns `BaseTool` but is typed as returning its decorated callable."""
    return value


def test_a_declared_prompt_is_published_block_by_block(
    project: LocalVariableProvider, wait_for_publish: Callable[[], None]
) -> None:
    middleware = agent_control(
        label='production',
        instructions={
            'role': 'You are a concise checkout assistant.',
            'today': lambda request: 'Today is Monday.',
        },
    )
    run(build_agent(RecordingModel(replies=[AIMessage('ok')]), middleware, tools=[], system_prompt=None))
    wait_for_publish()

    # Declared text is the agent as written, so it is published; a block the code computes per
    # request is published as the seam it is, and one run's rendering of it stays in that run.
    assert published_baseline(project)['instructions'] == snapshot(
        [
            {'id': 'system:role', 'instructions': 'You are a concise checkout assistant.', 'dynamic': False},
            {'id': 'system:today', 'dynamic': True},
        ]
    )
