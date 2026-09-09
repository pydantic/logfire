"""Naming the agent's config, declaring its prompt blocks, and binding the class."""

from __future__ import annotations

import pytest
from livekit.agents import Agent
from livekit.agents.llm.chat_context import Instructions

from logfire.agent_control.livekit import agent_control, instruction_blocks

from .agents import control_of, get_weather


def test_the_variable_is_named_after_the_agent() -> None:
    managed = agent_control(Agent, name='checkout-assistant', label='production')
    control = control_of(managed)
    assert (control.name, control.variable_name, control.label) == (
        'checkout-assistant',
        'agent__checkout_assistant',
        'production',
    )


def test_the_agent_name_is_required() -> None:
    with pytest.raises(ValueError, match='has nothing a variable key can be made of'):
        agent_control(name='')


def test_declared_blocks_become_the_prompt_as_written() -> None:
    instructions = instruction_blocks(
        {'agent': 'You are a checkout assistant.', 'refunds': 'Confirm the total.'},
        audio='Keep it short.',
    )
    assert isinstance(instructions, Instructions)
    assert instructions.common == 'You are a checkout assistant.\n\nConfirm the total.'
    assert instructions.render(modality='audio') == (
        'You are a checkout assistant.\n\nConfirm the total.\n\nKeep it short.'
    )


def test_assembling_no_blocks_is_refused() -> None:
    with pytest.raises(ValueError, match='needs at least one block to assemble'):
        instruction_blocks({})


def test_binding_keeps_the_class_it_was_given() -> None:
    @agent_control(name='checkout')
    class CheckoutAgent(Agent):
        """A checkout assistant."""

        def __init__(self) -> None:
            super().__init__(instructions='CODE', tools=[get_weather])

    agent = CheckoutAgent()
    assert isinstance(agent, Agent)
    assert CheckoutAgent.__name__ == 'CheckoutAgent'
    assert CheckoutAgent.__doc__ == 'A checkout assistant.'
    assert CheckoutAgent.__module__ == __name__
    # The LiveKit id every span is labelled with is derived from the class name, so it has to survive.
    assert agent.id == 'checkout_agent'


def test_a_class_can_be_bound_without_the_decorator() -> None:
    """The positional is the framework's own object, so a class defined elsewhere binds the same way."""

    class CheckoutAgent(Agent):
        def __init__(self) -> None:
            super().__init__(instructions='CODE')

    managed = agent_control(CheckoutAgent, name='checkout')
    assert managed is not CheckoutAgent and issubclass(managed, CheckoutAgent)
    assert managed().instructions == 'CODE'
    assert control_of(managed).variable_name == 'agent__checkout'


def test_binding_something_that_is_not_an_agent_is_refused() -> None:
    with pytest.raises(TypeError, match='manages a subclass of `livekit.agents.Agent`'):
        agent_control(dict, name='checkout')  # type: ignore[type-var]
