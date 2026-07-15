---
title: "Connect Smolagents to the AI Gateway"
description: "Send Smolagents model requests through the Logfire AI Gateway."
---

# Connect Smolagents to the AI Gateway

Send requests from your Smolagents agents through Logfire to track model usage and apply gateway spending limits.

[Smolagents](https://huggingface.co/docs/smolagents/) is Hugging Face's Python library for building AI agents that call tools and run multi-step tasks. The example points `OpenAIServerModel` at an OpenAI-compatible gateway route.

## Before you start

- Complete the [AI Gateway prerequisites](index.md#before-you-start), including setting `LOGFIRE_GATEWAY_API_KEY` in your terminal.
- Use an existing Smolagents project. Install the OpenAI extra with `pip install 'smolagents[openai]'`.

!!! note "Model data passes through Logfire"
    This configuration sends prompts, tool inputs, and model responses through the Logfire AI Gateway and the selected model provider. If gateway telemetry is enabled, Logfire stores the conversation content in your selected project. Calls to built-in providers count toward your gateway spend.

## Configure Smolagents

Set `api_key` to your gateway key and `api_base` to the OpenAI-compatible gateway route. Copy the route and a supported model name from the Gateway **Connect** tab.

```python title="smolagents-gateway.py" hl_lines="7-8" skip-run="true" skip-reason="external-connection"
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

## Verify it worked

Run the example from your terminal. It prints the agent's response. That confirms the client reached the gateway. Organization admins can also open **AI Engineering** > **Gateway** > **Spending** to see usage for the key. If telemetry is enabled, open the selected project's **Live** view to inspect the request trace.

## Troubleshooting

- **Python raises `KeyError: 'LOGFIRE_GATEWAY_API_KEY'`:** set the environment variable in the same terminal where you run the example.
- **The request returns an authentication or model error:** copy the URL and model name again from the Gateway **Connect** tab, and confirm that the selected route supports the OpenAI request format.
