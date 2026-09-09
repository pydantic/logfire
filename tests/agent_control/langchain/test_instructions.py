"""What a published `instructions` section does to the system message the model is sent."""

from __future__ import annotations

from typing import Any

import pytest
from inline_snapshot import snapshot
from langchain_core.messages import AIMessage, SystemMessage

from logfire.agent_control.langchain import agent_control
from logfire.variables.local import LocalVariableProvider

from .conftest import RecordingModel, build_agent, declared_prompt, publish, run, system_message


def sent(model: RecordingModel) -> Any:
    return system_message(model).content


def test_a_declared_block_is_the_one_the_config_can_replace(project: LocalVariableProvider) -> None:
    publish(project, {'instructions': [{'id': 'system:role', 'instructions': 'You are TERSE.'}]})
    model = RecordingModel(replies=[AIMessage('ok')])
    run(build_agent(model, agent_control(label='production'), tools=[], system_prompt=declared_prompt()))

    assert sent(model) == snapshot([{'type': 'text', 'text': 'You are TERSE.'}])


def test_a_block_nobody_declared_is_a_seam_the_config_may_not_pin(project: LocalVariableProvider) -> None:
    # A plain `system_prompt=` string reaches this middleware exactly the way a prompt another
    # middleware computed for this one request does, so it is treated as the second: the text is the
    # request's, an override on it would pin one rendering forever, and that is said out loud.
    publish(project, {'instructions': [{'id': 'system', 'instructions': 'You are TERSE.'}]})
    model = RecordingModel(replies=[AIMessage('ok')])
    agent = build_agent(model, agent_control(label='production'), tools=[])

    with pytest.warns(UserWarning, match="addresses instruction block 'system', which the agent recomputes"):
        run(agent)
    assert sent(model) == 'You are a helpful assistant.'


def test_a_string_prompt_stays_a_string_when_a_block_is_added(project: LocalVariableProvider) -> None:
    # A one-element content list is a different payload to every provider, and a different cache
    # prefix on the ones that cache. Managing the instructions is not a licence to change the shape.
    # The addition lands ahead of the undeclared block, which is where the contract keeps managed
    # text: inside the prefix a provider can cache, in front of whatever the request recomputes.
    publish(project, {'instructions': 'Escalate anything over $500 to a human.'})
    model = RecordingModel(replies=[AIMessage('ok')])
    run(build_agent(model, agent_control(label='production'), tools=[]))

    assert sent(model) == snapshot('Escalate anything over $500 to a human.\n\nYou are a helpful assistant.')


def test_an_addition_follows_the_blocks_the_code_declared(project: LocalVariableProvider) -> None:
    publish(project, {'instructions': 'Escalate anything over $500 to a human.'})
    model = RecordingModel(replies=[AIMessage('ok')])
    run(build_agent(model, agent_control(label='production'), tools=[], system_prompt=declared_prompt()))

    assert sent(model) == snapshot(
        [
            {'type': 'text', 'text': 'You are a helpful assistant.'},
            {'type': 'text', 'text': 'Escalate anything over $500 to a human.'},
        ]
    )


def test_dropping_the_only_block_leaves_no_system_message(project: LocalVariableProvider) -> None:
    publish(project, {'instructions': [{'id': 'system:role'}]})
    model = RecordingModel(replies=[AIMessage('ok')])
    run(build_agent(model, agent_control(label='production'), tools=[], system_prompt=declared_prompt()))

    assert [message.type for message in model.requests[0]['messages']] == ['human']


def test_a_structured_prompt_is_addressed_block_by_block(project: LocalVariableProvider) -> None:
    publish(
        project,
        {
            'instructions': [
                {'id': 'system:role', 'instructions': 'You are a refund specialist.'},
                {'id': 'system:totals'},
                'Escalate anything over $500 to a human.',
            ]
        },
    )
    prompt = SystemMessage(
        content=[
            {'type': 'text', 'text': 'You are a checkout assistant.', 'id': 'role'},
            {'type': 'text', 'text': 'Always confirm the order total.', 'id': 'totals'},
        ]
    )
    model = RecordingModel(replies=[AIMessage('ok')])
    run(build_agent(model, agent_control(label='production'), tools=[], system_prompt=prompt))

    assert sent(model) == snapshot(
        [
            {'type': 'text', 'text': 'You are a refund specialist.'},
            {'type': 'text', 'text': 'Escalate anything over $500 to a human.'},
        ]
    )


def test_a_replaced_block_keeps_its_cache_breakpoint(project: LocalVariableProvider) -> None:
    publish(project, {'instructions': [{'id': 'system:rules', 'instructions': 'Be brief.'}]})
    prompt = SystemMessage(
        content=[
            {'type': 'text', 'text': 'Be thorough.', 'id': 'rules', 'cache_control': {'type': 'ephemeral'}},
            {'type': 'image', 'source': {'type': 'url', 'url': 'https://example.com/logo.png'}},
        ]
    )
    model = RecordingModel(replies=[AIMessage('ok')])
    run(build_agent(model, agent_control(label='production'), tools=[], system_prompt=prompt))

    # The `id` is Agent Control's label and is stripped; `cache_control` is the user's own directive
    # and survives, as does content the adapter cannot read and does not offer to anyone.
    assert sent(model) == snapshot(
        [
            {'type': 'text', 'text': 'Be brief.', 'cache_control': {'type': 'ephemeral'}},
            {'type': 'image', 'source': {'type': 'url', 'url': 'https://example.com/logo.png'}},
        ]
    )


def test_content_the_config_cannot_edit_keeps_its_place_among_what_it_can(project: LocalVariableProvider) -> None:
    publish(project, {'instructions': [{'id': 'system:intro'}, 'Escalate anything over $500 to a human.']})
    prompt = SystemMessage(
        content=[
            {'type': 'text', 'text': 'You are a checkout assistant.', 'id': 'intro'},
            {'type': 'image', 'source': {'type': 'url', 'url': 'https://example.com/logo.png'}},
            {'type': 'text', 'text': 'Always confirm the order total.', 'id': 'totals'},
        ]
    )
    model = RecordingModel(replies=[AIMessage('ok')])
    run(build_agent(model, agent_control(label='production'), tools=[], system_prompt=prompt))

    # The removed block takes its entry with it, the image stays between what is left of the text,
    # and the added block lands at the end of the run of blocks the code declared.
    assert sent(model) == snapshot(
        [
            {'type': 'image', 'source': {'type': 'url', 'url': 'https://example.com/logo.png'}},
            {'type': 'text', 'text': 'Always confirm the order total.'},
            {'type': 'text', 'text': 'Escalate anything over $500 to a human.'},
        ]
    )


def test_block_ids_are_stripped_even_with_nothing_published(project: LocalVariableProvider) -> None:
    # OpenAI forwards content blocks verbatim, so an `id` added to make a block addressable would
    # otherwise become an unknown field on every request the agent makes.
    model = RecordingModel(replies=[AIMessage('ok')])
    run(build_agent(model, agent_control(label='production'), tools=[], system_prompt=declared_prompt()))

    assert sent(model) == snapshot([{'type': 'text', 'text': 'You are a helpful assistant.'}])


def test_a_prompt_with_no_ids_is_left_exactly_as_it_was(project: LocalVariableProvider) -> None:
    prompt = SystemMessage(content=[{'type': 'text', 'text': 'You are a checkout assistant.'}])
    model = RecordingModel(replies=[AIMessage('ok')])
    run(build_agent(model, agent_control(label='production'), tools=[], system_prompt=prompt))

    assert system_message(model) is prompt


def test_a_plain_string_block_in_a_content_list_is_a_seam_too(project: LocalVariableProvider) -> None:
    publish(project, {'instructions': [{'id': 'system:0', 'instructions': 'You are TERSE.'}]})
    model = RecordingModel(replies=[AIMessage('ok')])
    prompt = SystemMessage(content=['You are a checkout assistant.'])
    agent = build_agent(model, agent_control(label='production'), tools=[], system_prompt=prompt)

    with pytest.warns(UserWarning, match="addresses instruction block 'system:0', which the agent recomputes"):
        run(agent)
    assert sent(model) == ['You are a checkout assistant.']


def test_a_declared_block_can_be_a_plain_string_entrys_neighbour(project: LocalVariableProvider) -> None:
    publish(project, {'instructions': [{'id': 'system:rules', 'instructions': 'Be brief.'}]})
    model = RecordingModel(replies=[AIMessage('ok')])
    prompt = SystemMessage(content=['You are a checkout assistant.', {'type': 'text', 'text': '...', 'id': 'rules'}])
    run(build_agent(model, agent_control(label='production'), tools=[], system_prompt=prompt))

    assert sent(model) == snapshot(['You are a checkout assistant.', {'type': 'text', 'text': 'Be brief.'}])


def test_an_agent_with_no_prompt_can_still_be_given_one(project: LocalVariableProvider) -> None:
    publish(project, {'instructions': 'You are TERSE.'})
    model = RecordingModel(replies=[AIMessage('ok')])
    run(build_agent(model, agent_control(label='production'), tools=[], system_prompt=None))

    assert sent(model) == 'You are TERSE.'


def test_an_id_this_prompt_does_not_carry_is_reported(project: LocalVariableProvider) -> None:
    publish(project, {'instructions': [{'id': 'system:intro', 'instructions': 'You are TERSE.'}]})
    model = RecordingModel(replies=[AIMessage('ok')])
    agent = build_agent(model, agent_control(label='production'), tools=[], system_prompt=declared_prompt())

    with pytest.warns(UserWarning, match="addresses instruction block 'system:intro', which this request does not"):
        run(agent)
    assert sent(model) == [{'type': 'text', 'text': 'You are a helpful assistant.'}]


def test_a_declared_prompt_is_assembled_onto_a_request_that_has_none(project: LocalVariableProvider) -> None:
    model = RecordingModel(replies=[AIMessage('ok')])
    control = agent_control(
        label='production',
        instructions={'role': 'You are a checkout assistant.', 'refunds': 'Always confirm the order total.'},
    )
    run(build_agent(model, control, tools=[], system_prompt=None))

    # One string, in the order it was declared: what the code would have passed `create_agent`.
    assert sent(model) == snapshot('You are a checkout assistant.\n\nAlways confirm the order total.')


def test_each_declared_block_can_be_replaced_or_removed_on_its_own(project: LocalVariableProvider) -> None:
    publish(
        project,
        {
            'instructions': [
                {'id': 'system:role', 'instructions': 'You are a refund specialist.'},
                {'id': 'system:refunds'},
            ]
        },
    )
    model = RecordingModel(replies=[AIMessage('ok')])
    control = agent_control(
        label='production',
        instructions={'role': 'You are a checkout assistant.', 'refunds': 'Always confirm the order total.'},
    )
    run(build_agent(model, control, tools=[], system_prompt=None))

    assert sent(model) == 'You are a refund specialist.'


def test_a_declared_callable_is_a_seam_the_config_may_not_pin(project: LocalVariableProvider) -> None:
    publish(project, {'instructions': [{'id': 'system:today', 'instructions': 'Today is never.'}]})
    days = iter(['Monday', 'Tuesday'])
    model = RecordingModel(
        replies=[
            AIMessage(content='', tool_calls=[{'name': 'get_time', 'args': {'city': 'Paris'}, 'id': 'c1'}]),
            AIMessage('done'),
        ]
    )
    control = agent_control(
        label='production',
        instructions={'role': 'You are a checkout assistant.', 'today': lambda request: f'Today is {next(days)}.'},
    )
    agent = build_agent(model, control, system_prompt=None)

    with pytest.warns(UserWarning, match="addresses instruction block 'system:today', which the agent recomputes"):
        run(agent)
    # Recomputed per request, and the fixed block stays ahead of it.
    assert [request['messages'][0].text for request in model.requests] == snapshot(
        [
            'You are a checkout assistant.\n\nToday is Monday.',
            'You are a checkout assistant.\n\nToday is Tuesday.',
        ]
    )


def test_a_declared_callable_sees_the_request_it_is_computing_for(project: LocalVariableProvider) -> None:
    model = RecordingModel(replies=[AIMessage('ok')])
    control = agent_control(label='production', instructions={'ask': lambda request: request.messages[0].text.upper()})
    run(build_agent(model, control, tools=[], system_prompt=None))

    assert sent(model) == 'WEATHER IN PARIS?'


def test_an_addition_lands_between_the_declared_blocks_and_the_computed_ones(
    project: LocalVariableProvider,
) -> None:
    publish(project, {'instructions': 'Escalate anything over $500 to a human.'})
    model = RecordingModel(replies=[AIMessage('ok')])
    control = agent_control(
        label='production',
        instructions={'role': 'You are a checkout assistant.', 'today': lambda request: 'Today is Monday.'},
    )
    run(build_agent(model, control, tools=[], system_prompt=None))

    assert sent(model) == snapshot(
        'You are a checkout assistant.\n\nEscalate anything over $500 to a human.\n\nToday is Monday.'
    )


def test_declaring_the_prompt_twice_says_so(project: LocalVariableProvider) -> None:
    model = RecordingModel(replies=[AIMessage('ok')])
    control = agent_control(label='production', instructions={'role': 'You are a checkout assistant.'})
    agent = build_agent(model, control, tools=[])

    with pytest.raises(ValueError, match='the request already carries a system message of its own'):
        run(agent)
