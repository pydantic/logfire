---
title: "AI Gateway: Instructor"
description: "Route Instructor model calls through the Logfire AI Gateway."
---

# Instructor

[Instructor](https://python.useinstructor.com/) is a Python library for extracting structured, typed data from large language model (LLM) responses — you describe the shape of the data you want and Instructor handles the rest. Because Instructor wraps a standard OpenAI client, routing through the gateway is just a matter of configuring that underlying client with the gateway URL. Set `LOGFIRE_GATEWAY_API_KEY` to a key from the Gateway **API Keys** tab before running this example.

```python title="instructor-gateway.py" skip-run="true" skip-reason="external-connection"
import os

import instructor
from openai import OpenAI
from pydantic import BaseModel


class Weather(BaseModel):
    city: str
    condition: str


client = instructor.from_openai(
    OpenAI(
        api_key=os.environ["LOGFIRE_GATEWAY_API_KEY"],
        base_url="https://gateway-us.pydantic.dev/proxy/openai",
    )
)

weather = client.create(
    model="gpt-5.4-mini",
    response_model=Weather,
    messages=[{"role": "user", "content": "What is the weather in London?"}],
)

print(weather)
```
