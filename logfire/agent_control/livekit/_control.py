"""The one function a LiveKit user calls: name the agent's config, and bind its class to it."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, TypeVar, cast, overload

from livekit.agents.voice import Agent

from .. import AgentControl, OnUnmatched
from ._agent import ManagedAgent

if TYPE_CHECKING:
    from logfire import Logfire

AgentT = TypeVar('AgentT', bound=Agent)


@overload
def agent_control(
    agent_cls: type[AgentT],
    *,
    name: str,
    label: str | None = None,
    on_unmatched: OnUnmatched = 'warn',
    publish_baseline: bool = True,
    logfire_instance: Logfire | None = None,
) -> type[AgentT]: ...


@overload
def agent_control(
    agent_cls: None = None,
    *,
    name: str,
    label: str | None = None,
    on_unmatched: OnUnmatched = 'warn',
    publish_baseline: bool = True,
    logfire_instance: Logfire | None = None,
) -> Callable[[type[AgentT]], type[AgentT]]: ...


def agent_control(
    agent_cls: type[AgentT] | None = None,
    *,
    name: str,
    label: str | None = None,
    on_unmatched: OnUnmatched = 'warn',
    publish_baseline: bool = True,
    logfire_instance: Logfire | None = None,
) -> type[AgentT] | Callable[[type[AgentT]], type[AgentT]]:
    """Make one LiveKit agent class's instructions, model, settings, and tool descriptions editable in Logfire.

    ```python
    from livekit.agents import Agent
    from livekit.plugins import openai
    from logfire.agent_control.livekit import agent_control


    @agent_control(name='checkout_assistant', label='production')
    class CheckoutAgent(Agent):
        def __init__(self) -> None:
            super().__init__(
                instructions='You are a concise checkout assistant.',
                llm=openai.LLM(model='gpt-4.1'),
            )
    ```

    A class is what LiveKit's own shape asks for: `llm_node` is a method, and a handoff moves the
    conversation to a *different* `Agent` class, so a managed agent is a class rather than a session
    or a worker. Bind each class you want managed, under a config name of its own.

    Args:
        agent_cls: The agent class to manage. Leave it out to use this as a decorator; pass it to
            bind a class you already have, as `agent_control(CheckoutAgent, name=...)`.
        name: The agent's name, which its config is stored under. Required and explicit: LiveKit's
            own `Agent(id=...)` is silently ignored on the base `Agent` class -- every one of them
            reports `default_agent` -- so a name taken from the agent would point half the agents in
            a worker at one config. Pass the name you want to see in Logfire.
        label: The label to resolve, such as `'production'`. When `None`, the variable's own
            targeting rules and rollout choose which label this process gets.
        on_unmatched: What to do about a published entry this agent cannot apply -- warn once
            (the default), raise, or ignore.
        publish_baseline: Whether to publish the code baseline the Logfire editor diffs against.
        logfire_instance: The Logfire instance to resolve and publish through. Defaults to the
            global one, which is what `logfire.configure()` sets up.

    Returns:
        The agent class, managed: a subclass that keeps the original's name -- and so its LiveKit
        `id`, which every span is labelled with -- and calls into it, so the agent's own `on_enter`
        and its own `llm_node` still run, whether or not anything is published.

    Raises:
        TypeError: When what it is given is not a subclass of `livekit.agents.Agent`.
    """
    control = AgentControl(
        name,
        label=label,
        logfire_instance=logfire_instance,
        on_unmatched=on_unmatched,
        publish_baseline=publish_baseline,
    )

    def bind(agent_cls: type[AgentT]) -> type[AgentT]:
        if not (isinstance(agent_cls, type) and issubclass(agent_cls, Agent)):  # pyright: ignore[reportUnnecessaryIsInstance]
            raise TypeError(f'`agent_control` manages a subclass of `livekit.agents.Agent`, not {agent_cls!r}.')
        managed = type(
            agent_cls.__name__,
            (ManagedAgent, agent_cls),
            {
                '_agent_control': control,
                '__module__': agent_cls.__module__,
                '__qualname__': agent_cls.__qualname__,
                '__doc__': agent_cls.__doc__,
            },
        )
        # The subclass is `agent_cls` plus overrides of three of its methods, which is exactly what
        # the decorated name should keep being to everything that uses it.
        return cast('type[AgentT]', managed)

    return bind if agent_cls is None else bind(agent_cls)
