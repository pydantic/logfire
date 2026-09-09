from .. import Block as Block
from collections.abc import Sequence
from google.adk.agents.llm_agent import LlmAgent
from google.adk.agents.readonly_context import ReadonlyContext

AGENT_BLOCK_ID: str
GLOBAL_BLOCK_ID: str
STATIC_BLOCK_ID: str
IDENTITY_BLOCK_ID: str

def identity_text(agent: LlmAgent) -> str:
    """The identity line ADK appends for this agent, or `''` when it appends none.

    Reproduced rather than matched by pattern, because reproducing it is what makes the line
    addressable *and* keeps the surrounding partition honest: a line guessed at wrongly would
    swallow the planner's and the tools' text into the same block.
    """
async def agent_sources(agent: LlmAgent, context: ReadonlyContext) -> list[Block]:
    """The named pieces of prompt this request assembles, in the order ADK appends them.

    A piece whose text this adapter cannot reproduce -- an `InstructionProvider` callable, a static
    instruction with non-text parts -- comes back with empty text and `dynamic=True`: enough for the
    baseline to tell the editor the block exists and is not theirs to change, and never matched
    against the joined prompt.

    The global instruction is read off the *root* agent, because that is the one ADK appends to every
    agent in the tree, including this one.
    """
def partition(system_instruction: str, sources: Sequence[Block]) -> list[Block]:
    """Slice a joined system instruction into the blocks a published config can address.

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
def join(blocks: Sequence[Block]) -> str:
    """Put the blocks back the way ADK joined them, which is what leaves an unmanaged request identical."""
def baseline_blocks(sources: Sequence[Block], located: Sequence[Block]) -> list[Block]:
    """The blocks to describe in the baseline: every source, located or not.

    A source the partition could not find is still part of the agent as written, and the editor needs
    to see that it exists and cannot be changed rather than not see it at all. It is described as
    dynamic, which is what it is here: text this adapter could not reproduce from the agent, and so
    text a published value must not replace.
    """
