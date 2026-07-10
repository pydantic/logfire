---
title: "AI Gateway: Microsoft Agent Framework"
description: "Route Microsoft Agent Framework model calls through the Logfire AI Gateway."
---

# Microsoft Agent Framework

[Microsoft Agent Framework](https://learn.microsoft.com/en-us/agent-framework/) is Microsoft's SDK for building multi-agent AI applications. To route its model calls through the Logfire AI Gateway, configure its OpenAI chat completion client with the gateway URL, using a key from the Gateway **API Keys** tab.

## Python

```python title="microsoft-agent-framework-gateway.py" skip-run="true" skip-reason="external-connection"
import asyncio
import os

from agent_framework.openai import OpenAIChatCompletionClient


async def main() -> None:
    agent = OpenAIChatCompletionClient(
        model='gpt-5.4-mini',
        api_key=os.environ['LOGFIRE_GATEWAY_API_KEY'],
        base_url='https://gateway-us.pydantic.dev/proxy/openai',
    ).as_agent(
        name='WeatherAgent',
        instructions='You are a concise weather assistant.',
    )
    result = await agent.run('What is the weather in London?')
    print(result)


if __name__ == '__main__':
    asyncio.run(main())
```

## .NET {#dotnet}

```csharp title="microsoft-agent-framework-gateway.cs" skip-run="true" skip-reason="external-connection"
using Microsoft.Agents.AI;
using OpenAI;
using OpenAI.Chat;

using var cts = new CancellationTokenSource(TimeSpan.FromSeconds(60));

var apiKey = Environment.GetEnvironmentVariable("LOGFIRE_GATEWAY_API_KEY");
if (string.IsNullOrWhiteSpace(apiKey))
{
    throw new InvalidOperationException("LOGFIRE_GATEWAY_API_KEY is required");
}

OpenAIClientOptions options = new()
{
    Endpoint = new Uri("https://gateway-us.pydantic.dev/proxy/openai")
};

OpenAIClient client = new(
    new System.ClientModel.ApiKeyCredential(apiKey),
    options
);

var chatClient = client.GetChatClient("gpt-5.4-mini");
AIAgent agent = chatClient.AsAIAgent(
    instructions: "You are a concise weather assistant.",
    name: "WeatherAgent"
);

Console.WriteLine(await agent.RunAsync("What is the weather in London?", cancellationToken: cts.Token));
```
