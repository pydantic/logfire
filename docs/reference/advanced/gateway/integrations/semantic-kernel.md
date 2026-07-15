---
title: "Connect Semantic Kernel to the AI Gateway"
description: "Send Semantic Kernel model requests through the Logfire AI Gateway."
---

# Connect Semantic Kernel to the AI Gateway

Send requests from your Semantic Kernel application through Logfire to track model usage and apply spending limits.

[Microsoft Semantic Kernel](https://learn.microsoft.com/en-us/semantic-kernel/) is an SDK for adding AI models to applications. Both examples configure its OpenAI chat completion service with an OpenAI-compatible gateway route.

## Before you start

- Complete the [AI Gateway prerequisites](index.md#before-you-start), including setting `LOGFIRE_GATEWAY_API_KEY` in your terminal.
- Use an existing Semantic Kernel project with the packages imported by your chosen example installed.

!!! note "Model data passes through Logfire"
    This configuration sends prompts and model responses through the Logfire AI Gateway and the selected model provider. If gateway telemetry is enabled, Logfire stores the conversation content in your selected project. Calls to built-in providers count toward your gateway spend.

## Python

Set `api_key` to your gateway key and `base_url` to the OpenAI-compatible gateway route. Copy the route and a supported model name from the Gateway **Connect** tab.

```python title="semantic-kernel-gateway.py" hl_lines="14-15" skip-run="true" skip-reason="external-connection"
import asyncio
import os

from openai import AsyncOpenAI
from semantic_kernel.connectors.ai.open_ai import OpenAIChatCompletion
from semantic_kernel.connectors.ai.open_ai.prompt_execution_settings.open_ai_prompt_execution_settings import (
    OpenAIChatPromptExecutionSettings,
)
from semantic_kernel.contents.chat_history import ChatHistory

chat_completion = OpenAIChatCompletion(
    ai_model_id='gpt-5.4-mini',
    async_client=AsyncOpenAI(
        api_key=os.environ['LOGFIRE_GATEWAY_API_KEY'],
        base_url='https://gateway-us.pydantic.dev/proxy/openai',
    ),
)


async def main() -> None:
    history = ChatHistory()
    history.add_user_message('What is the weather in London?')
    response = await chat_completion.get_chat_message_content(
        chat_history=history,
        settings=OpenAIChatPromptExecutionSettings(),
    )
    print(response)


if __name__ == '__main__':
    asyncio.run(main())
```

## .NET {#dotnet}

Pass the same gateway key, route, and model name to `AddOpenAIChatCompletion`.

```csharp title="semantic-kernel-gateway.cs" hl_lines="8 17-18" skip-run="true" skip-reason="external-connection"
using Microsoft.SemanticKernel;
using Microsoft.SemanticKernel.ChatCompletion;

#pragma warning disable SKEXP0010

using var cts = new CancellationTokenSource(TimeSpan.FromSeconds(60));

var apiKey = Environment.GetEnvironmentVariable("LOGFIRE_GATEWAY_API_KEY");
if (string.IsNullOrWhiteSpace(apiKey))
{
    throw new InvalidOperationException("LOGFIRE_GATEWAY_API_KEY is required");
}

var builder = Kernel.CreateBuilder();
builder.AddOpenAIChatCompletion(
    modelId: "gpt-5.4-mini",
    apiKey: apiKey,
    endpoint: new Uri("https://gateway-us.pydantic.dev/proxy/openai")
);

Kernel kernel = builder.Build();
IChatCompletionService chat = kernel.GetRequiredService<IChatCompletionService>();
ChatHistory history = new();
history.AddUserMessage("What is the weather in London?");

var response = await chat.GetChatMessageContentAsync(history, kernel: kernel, cancellationToken: cts.Token);
Console.WriteLine(response.Content);
```

## Verify it worked

Run either example from your terminal. It prints the model response. That confirms the client reached the gateway. Organization admins can also open **AI Engineering** > **Gateway** > **Spending** to see usage for the key. If telemetry is enabled, open the selected project's **Live** view to inspect the request trace.

## Troubleshooting

- **The example reports that `LOGFIRE_GATEWAY_API_KEY` is missing:** set the environment variable in the same terminal where you run the example.
- **The request returns an authentication or model error:** copy the URL and model name again from the Gateway **Connect** tab, and confirm that the selected route supports the OpenAI request format.
