---
title: "Connect Microsoft Agent Framework to the AI Gateway"
description: "Send Microsoft Agent Framework model requests through the Logfire AI Gateway."
---

# Connect Microsoft Agent Framework to the AI Gateway

Send requests from your Microsoft Agent Framework agents through Logfire to track model usage and apply spending limits.

[Microsoft Agent Framework](https://learn.microsoft.com/en-us/agent-framework/) is Microsoft's SDK for building multi-agent AI applications. Both examples point an OpenAI chat completion client at an OpenAI-compatible gateway route.

## Before you start

- Complete the [AI Gateway prerequisites](index.md#before-you-start), including setting `LOGFIRE_GATEWAY_API_KEY` in your terminal.
- Use an existing Microsoft Agent Framework project with the packages imported by your chosen example installed.

!!! note "Model data passes through Logfire"
    This configuration sends prompts, tool inputs, and model responses through the Logfire AI Gateway and the selected model provider. If gateway telemetry is enabled, Logfire stores the conversation content in your selected project. Calls to built-in providers count toward your gateway spend.

## Python

Set `api_key` to your gateway key and `base_url` to the OpenAI-compatible gateway route. Copy the route and a supported model name from the Gateway **Connect** tab.

```python title="microsoft-agent-framework-gateway.py" hl_lines="10-11" skip-run="true" skip-reason="external-connection"
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

Pass the same key and route to the .NET `OpenAIClient`.

```csharp title="microsoft-agent-framework-gateway.cs" hl_lines="7 15 19" skip-run="true" skip-reason="external-connection"
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

## Verify it worked

Run either example from your terminal. It prints the agent's response. That confirms the client reached the gateway. Organization admins can also open **AI Engineering** > **Gateway** > **Spending** to see usage for the key. If telemetry is enabled, open the selected project's **Live** view to inspect the request trace.

## Troubleshooting

- **The example reports that `LOGFIRE_GATEWAY_API_KEY` is missing:** set the environment variable in the same terminal where you run the example.
- **The request returns an authentication or model error:** copy the URL and model name again from the Gateway **Connect** tab, and confirm that the selected route supports the OpenAI request format.
