"""Logfire Agent Control for the Claude Agent SDK.

Wrap the `ClaudeAgentOptions` you already build, and an agent's system prompt, its subagents' prompts,
its model, how hard it thinks, and the descriptions its in-process tools show the model become
editable from the Logfire UI -- versioned, labelled, rolled out, and rolled back as one unit, without
a redeploy. Everything you do not change in Logfire keeps doing what your code says.

```python skip-run="true" skip-reason="illustrative-fragment"
from claude_agent_sdk import ClaudeAgentOptions, query
from logfire.agent_control.claude_agent_sdk import agent_control

options = agent_control(ClaudeAgentOptions(system_prompt='You are a checkout assistant.'), name='checkout_assistant')
async for message in query(prompt='Refund my last order.', options=options):
    ...
```

This SDK spawns the `claude` CLI and talks to it over stdio, so a config is applied where the SDK
builds that process's arguments: at session start, not per model request. See the Agent Control
documentation for what that means, and for the parts of a Claude Code agent no adapter can reach.
"""

from ._control import ManagedAgent, agent_control
from ._tools import sdk_mcp_server

__all__ = (
    'ManagedAgent',
    'agent_control',
    'sdk_mcp_server',
)
