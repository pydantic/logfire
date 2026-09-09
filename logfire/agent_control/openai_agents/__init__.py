"""Logfire Agent Control for the OpenAI Agents SDK.

Wrap an `Agent` in [`agent_control`][logfire.agent_control.openai_agents.agent_control] and its
instructions, its model, its model settings, and the descriptions its tools show the model become
editable from the Logfire UI -- versioned, labelled, rolled out, and rolled back as one unit, with no
redeploy. Everything not changed in Logfire keeps doing what the code says.

```python skip-run="true" skip-reason="illustrative-fragment"
from agents import Agent, Runner
from logfire.agent_control.openai_agents import agent_control

agent = agent_control(
    Agent(name='checkout_assistant', instructions='You are a concise checkout assistant.'),
    label='production',
)
result = await Runner.run(agent, 'Refund my last order.')
```
"""

from ._adapter import agent_control
from ._instructions import InstructionSource

__all__ = ('InstructionSource', 'agent_control')
