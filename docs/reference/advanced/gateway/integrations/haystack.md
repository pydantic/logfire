---
title: "AI Gateway: Haystack"
description: "Route Haystack model calls through the Logfire AI Gateway."
---

# Haystack

[Haystack](https://haystack.deepset.ai/) is an open-source Python framework for building AI search and document processing pipelines. To route its model calls through the Logfire AI Gateway, configure `OpenAIChatGenerator` with the gateway URL, using a key from the Gateway **API Keys** tab.

```python title="haystack-gateway.py" skip-run="true" skip-reason="external-connection"
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
