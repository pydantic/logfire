from _typeshed import Incomplete
from collections.abc import Mapping
from dataclasses import dataclass, field
from livekit.agents import llm
from livekit.agents.types import NotGivenOr
from typing import Any

@dataclass(frozen=True)
class Plugin:
    """What one LiveKit plugin family can be told, in the contract's vocabulary."""
    name: str
    extra_kwargs: Mapping[str, str] = field(default_factory=dict[str, str])
    thinking: str | None = ...
    parallel_tool_calls: bool = ...
    @property
    def supported(self) -> frozenset[str]:
        """The canonical keys this family can apply, for `apply_settings(supported=...)`."""

PLUGINS: Incomplete
UNKNOWN: Incomplete

def plugin_for(model: llm.LLM | llm.RealtimeModel) -> Plugin:
    """The family `model` belongs to, by where the class it inherits its `chat()` from is defined.

    The whole ancestry rather than the class itself, because a plugin's `LLM` is routinely wrapped:
    `openai.LLM.with_azure` and friends return the same class, and an application that subclasses one
    to log or retry around `chat()` is still sending that provider's request.
    """
def constructor_value(model: llm.LLM | llm.RealtimeModel, name: str) -> Any:
    """What the plugin's constructor already set for the `extra_kwargs` key `name`, or `NOT_GIVEN`.

    Reaching into `_opts` is the only way to see a collision coming: the plugins expose no getter, and
    the alternative is letting a published setting silently lose to code on every request.
    """

@dataclass(frozen=True)
class Lowered:
    """The published settings, in the three shapes `LLM.chat` takes them in."""
    extra_kwargs: dict[str, Any] = field(default_factory=dict[str, Any])
    parallel_tool_calls: NotGivenOr[bool] = ...
    timeout: float | None = ...

def lower(settings: Mapping[str, Any], model: llm.LLM, plugin: Plugin) -> tuple[Lowered, list[str]]:
    """Lower canonical settings for `model`, with the collisions the plugin will win to report.

    `settings` has already been filtered to the keys the family supports, so everything here has a
    name to go under; what is left to decide is whether the constructor already claimed that name, and
    whether an effort level has a level-shaped knob to go into.
    """
def code_settings(model: llm.LLM, plugin: Plugin) -> dict[str, Any]:
    """The settings the plugin was constructed with, in canonical names.

    Read back through the same table that lowers them, so this describes exactly the knobs a
    published value would reach. `timeout` is not here: LiveKit keeps it on the session's connection
    options rather than on the model, so whoever needs it reads it from there.

    Values are passed on as the plugin holds them, including ones the contract has no room for -- an
    OpenAI reasoning model's default `reasoning_effort` of `'none'` is not one of the effort levels.
    Naming it and letting `canonical_settings` drop and report it is the contract's rule for an
    unrepresentable value; deciding here would be this package approximating on its own.
    """
def carry_settings(code_model: llm.LLM, plugin: Plugin) -> tuple[dict[str, Any], list[str]]:
    '''The code model\'s settings that `plugin` can be told, and messages for the ones it cannot.

    A published `model` is a fresh plugin instance carrying its class\'s defaults, so the temperature
    and token budget someone chose in code would silently go away with the model they were set on --
    turning "run this on a different model" into "and reset everything else". They are the code side
    of the same contract, so they move across as per-request settings, underneath the published
    `settings` section, which is what overriding code means.

    A setting the replacement\'s plugin family has no name for (an Anthropic `top_k` on the way to
    OpenAI) cannot move, and is reported rather than dropped: the agent really is about to run
    without something its code asked for.
    '''
