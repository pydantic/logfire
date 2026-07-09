---
title: "AI Gateway: Agno"
description: "Route Agno model calls through the Logfire AI Gateway."
---

# Agno

[Agno](https://docs.agno.com/) is a Python framework for building multi-modal, multi-agent AI systems. To route its model calls through the Logfire AI Gateway, configure `OpenAIChat` with the gateway URL and set `LOGFIRE_GATEWAY_API_KEY` to a key from the Gateway **API Keys** tab.

```python title="agno-gateway.py" skip-run="true" skip-reason="external-connection"
import os

from agno.agent import Agent
from agno.models.openai import OpenAIChat

agent = Agent(
    name="Weather Agent",
    model=OpenAIChat(
        id="gpt-5.4-mini",
        api_key=os.environ["LOGFIRE_GATEWAY_API_KEY"],
        base_url="https://gateway-us.pydantic.dev/proxy/openai",
    ),
)

agent.print_response("What is the weather in London?")
```
