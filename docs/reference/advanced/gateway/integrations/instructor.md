---
title: "Connect Instructor to the AI Gateway"
description: "Send Instructor model requests through the Logfire AI Gateway."
---

# Connect Instructor to the AI Gateway

Send Instructor's structured-output requests through Logfire to track model usage and apply spending limits.

[Instructor](https://python.useinstructor.com/) is a Python library for extracting structured, typed data from LLM responses. You describe the data shape, and Instructor validates the model's response against it. Because Instructor wraps an OpenAI client, you connect the underlying client to an OpenAI-compatible gateway route.

## Before you start

- Complete the [AI Gateway prerequisites](index.md#before-you-start), including setting `LOGFIRE_GATEWAY_API_KEY` in your terminal.
- Use an existing Instructor project with the packages imported below installed.

!!! note "Model data passes through Logfire"
    This configuration sends prompts and model responses through the Logfire AI Gateway and the selected model provider. If gateway telemetry is enabled, Logfire stores the conversation content in your selected project. Calls to built-in providers count toward your gateway spend.

## Configure Instructor

Set the wrapped OpenAI client's `api_key` to your gateway key and `base_url` to the OpenAI-compatible gateway route. Copy the route and a supported model name from the Gateway **Connect** tab.

```python title="instructor-gateway.py" hl_lines="15-16" skip-run="true" skip-reason="external-connection"
import os

import instructor
from openai import OpenAI
from pydantic import BaseModel


class Weather(BaseModel):
    city: str
    condition: str


client = instructor.from_openai(
    OpenAI(
        api_key=os.environ['LOGFIRE_GATEWAY_API_KEY'],
        base_url='https://gateway-us.pydantic.dev/proxy/openai',
    )
)

weather = client.create(
    model='gpt-5.4-mini',
    response_model=Weather,
    messages=[{'role': 'user', 'content': 'What is the weather in London?'}],
)

print(weather)
```

## Verify it worked

Run the example from your terminal. It prints a validated `Weather` object. That confirms the client reached the gateway. Organization admins can also open **AI Engineering** > **Gateway** > **Spending** to see usage for the key. If telemetry is enabled, open the selected project's **Live** view to inspect the request trace.

## Troubleshooting

- **Python raises `KeyError: 'LOGFIRE_GATEWAY_API_KEY'`:** set the environment variable in the same terminal where you run the example.
- **The request returns an authentication or model error:** copy the URL and model name again from the Gateway **Connect** tab, and confirm that the selected route supports the OpenAI request format.
