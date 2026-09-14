from .. import AgentControl as AgentControl, OnUnmatched as OnUnmatched
from ._agent import ManagedAgent as ManagedAgent
from collections.abc import Callable
from livekit.agents.voice import Agent
from logfire import Logfire as Logfire
from typing import TypeVar, overload

AgentT = TypeVar('AgentT', bound=Agent)

@overload
def agent_control(agent_cls: type[AgentT], *, name: str, label: str | None = None, on_unmatched: OnUnmatched = 'warn', publish_baseline: bool = True, logfire_instance: Logfire | None = None) -> type[AgentT]: ...
@overload
def agent_control(agent_cls: None = None, *, name: str, label: str | None = None, on_unmatched: OnUnmatched = 'warn', publish_baseline: bool = True, logfire_instance: Logfire | None = None) -> Callable[[type[AgentT]], type[AgentT]]: ...
