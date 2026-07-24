---
title: "Connect Haystack to the AI Gateway"
description: "Send Haystack model requests through the Logfire AI Gateway."
---

# Connect Haystack to the AI Gateway

Send requests from your Haystack pipelines through the Logfire AI Gateway.

[Haystack](https://haystack.deepset.ai/) is an open-source Python framework for AI search and document-processing pipelines. The example points `OpenAIChatGenerator` at an OpenAI-compatible gateway route.

## Before you start

- Complete the [AI Gateway prerequisites](index.md#before-you-start), including setting `LOGFIRE_GATEWAY_API_KEY` in your terminal.
- Use an existing Haystack project with the packages imported below installed.

!!! note "Model data passes through Logfire"
    This configuration sends prompts and model responses through the Logfire AI Gateway and the selected model provider. If gateway telemetry is enabled, Logfire stores the conversation content in your selected project. Calls to built-in providers count toward your gateway spend.

## Configure Haystack

Set `api_key` to your gateway key and `api_base_url` to the OpenAI-compatible gateway route. Copy the route and a supported model name from the Gateway **Connect** tab.

```python title="haystack-gateway.py" hl_lines="7-8" skip-run="true" skip-reason="external-connection"
from haystack.components.generators.chat import OpenAIChatGenerator
from haystack.dataclasses import ChatMessage
from haystack.utils import Secret

generator = OpenAIChatGenerator(
    model='gpt-5.4-mini',
    api_key=Secret.from_env_var('LOGFIRE_GATEWAY_API_KEY'),
    api_base_url='https://gateway-us.pydantic.dev/proxy/openai',
)

response = generator.run([ChatMessage.from_user('What is the weather in London?')])

print(response['replies'][0].text)
```

## Verify it worked

Run the example from your terminal. It prints the model response. That confirms the client reached the gateway. Organization admins can also open **AI Engineering** > **Gateway** > **Spending** to see usage for the key. If telemetry is enabled, open the selected project's **Live** view to inspect the request trace.

## Troubleshooting

- **Haystack cannot read `LOGFIRE_GATEWAY_API_KEY`:** set the environment variable in the same terminal where you run the example.
- **The request returns an authentication or model error:** copy the URL and model name again from the Gateway **Connect** tab, and confirm that the selected route supports the OpenAI request format.
