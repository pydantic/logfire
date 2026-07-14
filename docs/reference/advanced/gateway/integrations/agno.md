---
title: "Connect Agno to the AI Gateway"
description: "Send Agno model requests through the Logfire AI Gateway."
---

# Connect Agno to the AI Gateway

Send requests from your Agno agents through Logfire to track model usage and apply gateway spending limits.

[Agno](https://docs.agno.com/) is a Python framework for building multimodal and multi-agent AI systems. The example keeps the agent in Agno and points its `OpenAIChat` model at an OpenAI-compatible gateway route.

## Before you start

- Complete the [AI Gateway prerequisites](index.md#before-you-start), including setting `LOGFIRE_GATEWAY_API_KEY` in your terminal.
- Use an existing Agno project with the packages imported below installed.

!!! note "Model data passes through Logfire"
    This configuration sends prompts, tool inputs, and model responses through the Logfire AI Gateway and the selected model provider. If gateway telemetry is enabled, Logfire stores the conversation content in your selected project. Calls to built-in providers count toward your gateway spend.

## Configure Agno

Set `api_key` to your gateway key and `base_url` to the OpenAI-compatible gateway route. Copy the route and a supported model name from the Gateway **Connect** tab.

```python title="agno-gateway.py" hl_lines="10-11" skip-run="true" skip-reason="external-connection"
import os

from agno.agent import Agent
from agno.models.openai import OpenAIChat

agent = Agent(
    name='Weather Agent',
    model=OpenAIChat(
        id='gpt-5.4-mini',
        api_key=os.environ['LOGFIRE_GATEWAY_API_KEY'],
        base_url='https://gateway-us.pydantic.dev/proxy/openai',
    ),
)

agent.print_response('What is the weather in London?')
```

## Verify it worked

Run the example from your terminal. It prints the model response. That confirms the client reached the gateway. Organization admins can also open **AI Engineering** > **Gateway** > **Spending** to see usage for the key. If telemetry is enabled, open the selected project's **Live** view to inspect the request trace.

## Troubleshooting

- **Python raises `KeyError: 'LOGFIRE_GATEWAY_API_KEY'`:** set the environment variable in the same terminal where you run the example.
- **The request returns an authentication or model error:** copy the URL and model name again from the Gateway **Connect** tab, and confirm that the selected route supports the OpenAI request format.
