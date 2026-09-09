r"""Finding the seams in an ADK system instruction, so a published block can replace one piece of it.

ADK assembles a prompt from several named sources -- a global instruction, a static instruction, the
agent's own instruction, the identity line it writes itself, and whatever the planner and the tools
append -- and joins all of it into one string with `"\n\n"` before any hook can see it. The config
addresses blocks by id, so the adapter has to put the seams back.

It does that by locating each source's text inside the joined string, in the order ADK appends them.
The join is verbatim, so a located source is an exact slice, and everything between two slices is
text the planner or a tool contributed, kept as an unaddressable block. Re-joining the blocks
therefore reproduces the prompt the agent would have sent, byte for byte, wherever nothing was
published.
"""

from __future__ import annotations

from collections.abc import Sequence

from google.adk.agents.llm_agent import LlmAgent
from google.adk.agents.readonly_context import ReadonlyContext
from google.adk.utils.instructions_utils import inject_session_state
from google.genai import types

from .. import Block

AGENT_BLOCK_ID = 'agent'
"""The agent's own `instruction`, and the one id the contract reserves across every framework."""

GLOBAL_BLOCK_ID = 'global'
"""The root agent's `global_instruction`, which ADK puts ahead of everything else."""

STATIC_BLOCK_ID = 'static'
"""The agent's `static_instruction`: the cache-stable prefix ADK sends before the dynamic text."""

IDENTITY_BLOCK_ID = 'identity'
r"""The line ADK writes itself from the agent's `name` and `description`.

Addressable like any other block, which is the only way to edit it: the text is ADK's, and the only
part of it the agent owns is `description`, which is not a prompt anyone can see in Logfire.
"""


def _content_text(content: types.ContentUnion) -> str:
    r"""The text `LlmRequest.append_instructions` joins a `static_instruction` down to.

    ADK accepts a `str`, a `Part`, a `Content`, or a list of those, and appends the text parts joined
    with `"\n\n"`. A non-text part becomes a generated reference line and its data moves into the
    request's contents, which is not text this adapter can address, so a static instruction carrying
    one is reported as unlocatable rather than half-matched.
    """
    if isinstance(content, str):
        return content
    parts: list[types.Part] = []
    if isinstance(content, types.Content):
        parts = list(content.parts or [])
    elif isinstance(content, types.Part):
        parts = [content]
    elif isinstance(content, list):
        items: list[object] = list(content)
        if not all(isinstance(item, types.Part) for item in items):
            return ''
        parts = [item for item in items if isinstance(item, types.Part)]
    else:
        return ''
    texts = [part.text for part in parts if part.text]
    return '\n\n'.join(texts) if len(texts) == len(parts) else ''


def identity_text(agent: LlmAgent) -> str:
    """The identity line ADK appends for this agent, or `''` when it appends none.

    Reproduced rather than matched by pattern, because reproducing it is what makes the line
    addressable *and* keeps the surrounding partition honest: a line guessed at wrongly would
    swallow the planner's and the tools' text into the same block.
    """
    if getattr(agent, 'mode', None) == 'single_turn':
        return ''
    text = f'You are an agent. Your internal name is "{agent.name}".'
    if agent.description:
        text += f' The description about you is "{agent.description}".'
    return text


async def _rendered(instruction: str, context: ReadonlyContext) -> Block | None:
    """Render an instruction the way ADK's assembly did, or `None` when this adapter cannot.

    An instruction carrying `{state}` placeholders is a third thing the contract has no word for: it
    is written statically but says something different on every request. Rendering it is what locates
    the block at all; reporting it as dynamic is what keeps a published value from pinning one
    request's rendering forever, and keeps a rendering built out of session state from reaching a
    baseline every member of the Logfire project can read.
    """
    try:
        rendered = await inject_session_state(instruction, context)
    except Exception:
        # ADK raises on a placeholder naming state the session does not carry -- but it raises during
        # assembly, long before this hook, so reaching here means only that this adapter cannot
        # reproduce what assembly produced. The block goes unlocated and the request stands.
        return None
    return Block(text=rendered, dynamic=rendered != instruction)


async def agent_sources(agent: LlmAgent, context: ReadonlyContext) -> list[Block]:
    """The named pieces of prompt this request assembles, in the order ADK appends them.

    A piece whose text this adapter cannot reproduce -- an `InstructionProvider` callable, a static
    instruction with non-text parts -- comes back with empty text and `dynamic=True`: enough for the
    baseline to tell the editor the block exists and is not theirs to change, and never matched
    against the joined prompt.

    The global instruction is read off the *root* agent, because that is the one ADK appends to every
    agent in the tree, including this one.
    """
    sources: list[Block] = []
    root = agent.root_agent
    global_instruction = root.global_instruction if isinstance(root, LlmAgent) else ''
    for block_id, instruction in ((GLOBAL_BLOCK_ID, global_instruction), (AGENT_BLOCK_ID, agent.instruction)):
        if not instruction:
            continue
        rendered = await _rendered(instruction, context) if isinstance(instruction, str) else None
        sources.append(
            Block(text='', id=block_id, dynamic=True)
            if rendered is None
            else Block(text=rendered.text, id=block_id, dynamic=rendered.dynamic)
        )
    if agent.static_instruction:
        text = _content_text(agent.static_instruction)
        sources.append(Block(text=text, id=STATIC_BLOCK_ID, dynamic=not text))
    if identity := identity_text(agent):
        sources.append(Block(text=identity, id=IDENTITY_BLOCK_ID, dynamic=False))
    # The loop above pairs the two instructions that need rendering; ADK sends them in a different
    # order, with the static instruction between them, so they are put back into request order here.
    order = {GLOBAL_BLOCK_ID: 0, STATIC_BLOCK_ID: 1, AGENT_BLOCK_ID: 2, IDENTITY_BLOCK_ID: 3}
    sources.sort(key=lambda source: order[source.id or ''])
    return sources


def _seam(system_instruction: str, text: str, cursor: int) -> int:
    r"""Where `text` sits in the joined prompt as a source of its own, or `-1` when it does not.

    A source is matched only where ADK could have appended it: at the very start of the prompt or
    just after one of the `"\n\n"` seams the join is made of, and ending at such a seam or at the end
    of the prompt. An unrestricted substring search would also match a source *inside* a longer piece
    of text -- a planner line quoting the agent's instruction back, an agent instruction that happens
    to be one sentence of the global one -- and a published block would then replace that occurrence,
    rewriting text belonging to something else and moving the block to where the false match was.
    """
    index = system_instruction.find(text, cursor)
    while index >= 0:
        end = index + len(text)
        starts_source = index == 0 or (index >= 2 and system_instruction[index - 2 : index] == '\n\n')
        ends_source = end == len(system_instruction) or system_instruction[end : end + 2] == '\n\n'
        if starts_source and ends_source:
            return index
        index = system_instruction.find(text, index + 1)
    return -1


def partition(system_instruction: str, sources: Sequence[Block]) -> list[Block]:
    r"""Slice a joined system instruction into the blocks a published config can address.

    Each source is looked for from where the previous one ended and only on the seams ADK's own join
    put there, so a source whose text also appears inside an earlier block is still matched at its
    own position. Text between two matches, and anything after the last one, becomes a block with no
    id and `dynamic=True`: nobody can address it, and marking it dynamic is what keeps an added block
    inside the prompt's cacheable static prefix instead of after a tool's per-request contribution.

    A source that is not found is left out. That is the `static_instruction` ADK routed the agent
    instruction around, a rendering this adapter could not reproduce, or an agent whose prompt one
    of its own callbacks has already rewritten -- in every case, text no published value may claim to
    be replacing.
    """
    blocks: list[Block] = []
    cursor = 0
    for source in sources:
        if not source.text:
            continue
        index = _seam(system_instruction, source.text, cursor)
        if index < 0:
            continue
        gap = system_instruction[cursor:index]
        if gap.endswith('\n\n'):
            gap = gap[:-2]
        if gap:
            blocks.append(Block(text=gap, dynamic=True))
        blocks.append(source)
        cursor = index + len(source.text)
        if system_instruction[cursor : cursor + 2] == '\n\n':
            cursor += 2
    if tail := system_instruction[cursor:]:
        blocks.append(Block(text=tail, dynamic=True))
    return blocks


def join(blocks: Sequence[Block]) -> str:
    """Put the blocks back the way ADK joined them, which is what leaves an unmanaged request identical."""
    return '\n\n'.join(block.text for block in blocks if block.text)


def baseline_blocks(sources: Sequence[Block], located: Sequence[Block]) -> list[Block]:
    """The blocks to describe in the baseline: every source, located or not.

    A source the partition could not find is still part of the agent as written, and the editor needs
    to see that it exists and cannot be changed rather than not see it at all. It is described as
    dynamic, which is what it is here: text this adapter could not reproduce from the agent, and so
    text a published value must not replace.
    """
    located_ids = {block.id for block in located}
    return [block if block.id in located_ids else Block(text='', id=block.id, dynamic=True) for block in sources]
