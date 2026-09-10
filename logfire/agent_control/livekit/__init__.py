"""Logfire Agent Control for LiveKit Agents.

Decorate a `livekit.agents.Agent` class with `agent_control`, and its instructions, its model, its
model settings, and the descriptions its tools show the model become editable from the Logfire UI --
versioned, labelled, rolled out, and rolled back as one unit, with no redeploy. Everything left
unchanged in Logfire keeps doing what the code says.
"""

from ._control import agent_control
from ._instructions import instruction_blocks

__all__ = ('agent_control', 'instruction_blocks')
