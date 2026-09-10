from .. import AgentControl as AgentControl, Block as Block, apply_instructions as apply_instructions, use_resolution as use_resolution
from ._run import current_run as current_run, resolve as resolve
from agents import Agent, RunContextWrapper
from collections.abc import Awaitable, Callable, Mapping, Sequence
from typing import Any, TypeAlias

InstructionSource: TypeAlias = str | Callable[[RunContextWrapper[Any], Agent[Any]], str | Awaitable[str]]
Sources: TypeAlias = tuple[tuple[str, InstructionSource], ...]
AGENT_BLOCK_ID: str
BLOCK_SEPARATOR: str

def order_sources(instructions: Mapping[str, InstructionSource]) -> Sources:
    """The declared blocks, fixed text first, each group in the order it was declared.

    Providers cache a request by its longest stable prefix, and a block computed per request is where
    that prefix ends. Sending the fixed blocks first therefore puts every one of them inside the
    cacheable prefix regardless of where in the mapping it was declared, and it is what makes a
    published *added* block land inside it too -- the core appends one after the last fixed block.
    """
def baseline_blocks(sources: Sources) -> list[Block]:
    """The blocks as the baseline describes them, which needs no run to know.

    A fixed block is its text; a computed one is a seam and a flag, since its text is one request's
    rendering of whatever that request carried and the baseline is read by everyone in the project.
    So the baseline never waits on a render, and an agent whose prompt varies with its input still
    publishes the same description of itself every time.
    """
def join_blocks(blocks: Sequence[Block]) -> str | None:
    """The blocks as the one prompt string the SDK sends, or `None` for an agent with no prompt."""
def instructions_renderer(control: AgentControl, sources: Sources) -> Callable[[RunContextWrapper[Any], Agent[Any]], Awaitable[str | None]]:
    """The `Agent.instructions` callable that renders the declared blocks and applies what is published.

    It applies the run's resolution rather than one of its own: the managed agent resolved once, at
    the top of this turn, and that same value is what the model wrapper applies to the tools, the
    settings and the model a moment later. Two resolutions in one request is exactly what the contract
    forbids -- a publish between them would send this prompt with the other sections' older version.
    Outside a run there is no record to read, so this falls back to resolving for itself.

    Rendering and applying happen inside the resolution's telemetry, so a block written as a function
    of the run emits its spans under the version that asked for it. What comes out is the prompt as it
    will be sent, so `RunHooks.on_llm_start` and `RunConfig.call_model_input_filter`, which both run
    after this, see the managed text and a filter that rewrites it still has the last word.
    """
