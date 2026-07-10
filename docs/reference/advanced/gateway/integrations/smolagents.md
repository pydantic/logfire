---
title: "AI Gateway: Smolagents"
description: "Route Smolagents model calls through the Logfire AI Gateway."
---

# Smolagents

[smolagents](https://huggingface.co/docs/smolagents/) is Hugging Face's lightweight Python library for building AI agents that call tools and run multi-step tasks. To route its model calls through the Logfire AI Gateway, configure `OpenAIServerModel` with the gateway URL, using a key from the Gateway **API Keys** tab.

```python title="smolagents-gateway.py" skip-run="true" skip-reason="external-connection"
import os

from smolagents import OpenAIServerModel, ToolCallingAgent

model = OpenAIServerModel(
    model_id='gpt-5.4-mini',
    api_base='https://gateway-us.pydantic.dev/proxy/openai',
    api_key=os.environ['LOGFIRE_GATEWAY_API_KEY'],
)
agent = ToolCallingAgent(tools=[], model=model)

print(agent.run('What is the weather in London?'))
```
