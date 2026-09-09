"""Logfire Agent Control for Google ADK.

Wrap an `LlmAgent` with `agent_control` and its instructions, its model, its model settings, and the
descriptions its tools show the model become editable from the Logfire UI -- versioned, labelled,
rolled out, and rolled back as one unit, with no redeploy. Everything not changed in Logfire keeps
doing what the code says.

Install with the `agent-control-google-adk` extra:

```bash
pip install 'logfire[agent-control-google-adk]'
```
"""

from ._adapter import agent_control

__all__ = ('agent_control',)
