"""Logfire Agent Control for LangChain's `create_agent`.

An agent's instructions, model, model settings, and tool descriptions become editable from the
Logfire UI -- versioned, labelled, rolled out, and rolled back as one unit, with no redeploy. This
module is one `AgentMiddleware`: add `agent_control()` last to `create_agent(middleware=[...])` and
the agent keeps doing exactly what its code says until someone publishes a value in Logfire.
"""

from ._instructions import Instruction
from ._middleware import AgentControlMiddleware, AgentControlState, agent_control

__all__ = ('AgentControlMiddleware', 'AgentControlState', 'Instruction', 'agent_control')
