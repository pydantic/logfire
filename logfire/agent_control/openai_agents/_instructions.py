"""Giving the SDK's single prompt the seams a managed config addresses blocks by.

`Agent.instructions` is one string or one callable, and the runner renders it to one string per model
request. That is enough for the `'agent'` block the contract reserves -- the prompt as written,
replaceable whole -- and nothing more: a prompt assembled from a role, a policy, and today's date has
no seams in it once joined, so nobody can edit the policy in Logfire without also pinning the date.

So the adapter owns prompt assembly. It installs an `Agent.instructions` callable of its own that
renders each declared block, applies the published `instructions` section to the blocks, and joins
the result -- which is also the only place it *can* happen: the model is handed the assembled prompt
and never the run context that a computed block needs. The value it applies is the run's, read back
out of the record the managed agent opened before this callable ran; see `_run`.
"""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable, Mapping, Sequence
from typing import Any, TypeAlias

from agents import Agent, RunContextWrapper

from .. import AgentControl, Block, apply_instructions, use_resolution
from ._run import current_run, resolve

InstructionSource: TypeAlias = str | Callable[[RunContextWrapper[Any], Agent[Any]], str | Awaitable[str]]
"""One instruction block as the agent declares it: fixed text, or a function of the run.

The callable form is the SDK's own `Agent.instructions` signature, so a prompt already written as a
function of the run context moves into a named block unchanged.
"""

Sources: TypeAlias = tuple[tuple[str, InstructionSource], ...]
"""The agent's prompt as named blocks, in the order they are sent."""

AGENT_BLOCK_ID = 'agent'
"""The id the contract reserves for the prompt as written, and the id an undeclared prompt gets."""

BLOCK_SEPARATOR = '\n\n'
"""What blocks are joined with, which is how a prompt written as one string already reads."""


def order_sources(instructions: Mapping[str, InstructionSource]) -> Sources:
    """The declared blocks, fixed text first, each group in the order it was declared.

    Providers cache a request by its longest stable prefix, and a block computed per request is where
    that prefix ends. Sending the fixed blocks first therefore puts every one of them inside the
    cacheable prefix regardless of where in the mapping it was declared, and it is what makes a
    published *added* block land inside it too -- the core appends one after the last fixed block.
    """
    return tuple(
        [(key, source) for key, source in instructions.items() if isinstance(source, str)]
        + [(key, source) for key, source in instructions.items() if not isinstance(source, str)]
    )


def baseline_blocks(sources: Sources) -> list[Block]:
    """The blocks as the baseline describes them, which needs no run to know.

    A fixed block is its text; a computed one is a seam and a flag, since its text is one request's
    rendering of whatever that request carried and the baseline is read by everyone in the project.
    So the baseline never waits on a render, and an agent whose prompt varies with its input still
    publishes the same description of itself every time.
    """
    return [
        Block(text=source, id=key, dynamic=False) if isinstance(source, str) else Block(text='', id=key, dynamic=True)
        for key, source in sources
    ]


def join_blocks(blocks: Sequence[Block]) -> str | None:
    """The blocks as the one prompt string the SDK sends, or `None` for an agent with no prompt."""
    if not blocks:
        return None
    return BLOCK_SEPARATOR.join(block.text for block in blocks if block.text)


async def _render(source: InstructionSource, run_context: RunContextWrapper[Any], agent: Agent[Any]) -> str:
    """One block's text for this request, calling and awaiting it the way the SDK would.

    Callable instances with an async `__call__` are not coroutine functions, so what comes back is
    checked for awaitability rather than the callable being checked for asyncness -- the same
    reasoning, and the same order, as `Agent.get_system_prompt`.
    """
    if isinstance(source, str):
        return source
    result = source(run_context, agent)
    if inspect.isawaitable(result):
        return await result
    return result


def instructions_renderer(
    control: AgentControl, sources: Sources
) -> Callable[[RunContextWrapper[Any], Agent[Any]], Awaitable[str | None]]:
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

    async def instructions(run_context: RunContextWrapper[Any], agent: Agent[Any]) -> str | None:
        run = current_run(control.variable_name)
        resolution = run.resolution if run is not None else resolve(control)
        with use_resolution(resolution):
            blocks = [
                Block(text=await _render(source, run_context, agent), id=key, dynamic=not isinstance(source, str))
                for key, source in sources
            ]
            config = resolution.config
            if config is not None:
                blocks = apply_instructions(blocks, config, on_unmatched=control.on_unmatched).blocks
            return join_blocks(blocks)

    return instructions
