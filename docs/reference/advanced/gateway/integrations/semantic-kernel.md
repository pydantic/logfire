---
title: "AI Gateway: Semantic Kernel"
description: "Route Semantic Kernel model calls through the Logfire AI Gateway."
---

# Semantic Kernel

[Microsoft Semantic Kernel](https://learn.microsoft.com/en-us/semantic-kernel/) is Microsoft's SDK for integrating AI models into your applications. To route its model calls through the Logfire AI Gateway, configure an OpenAI-compatible chat completion service with the gateway URL, using a key from the Gateway **API Keys** tab.

## Python

```python title="semantic-kernel-gateway.py" skip-run="true" skip-reason="external-connection"
import asyncio
import os

from openai import AsyncOpenAI
from semantic_kernel.connectors.ai.open_ai import OpenAIChatCompletion
from semantic_kernel.connectors.ai.open_ai.prompt_execution_settings.open_ai_prompt_execution_settings import (
    OpenAIChatPromptExecutionSettings,
)
from semantic_kernel.contents.chat_history import ChatHistory

chat_completion = OpenAIChatCompletion(
    ai_model_id="gpt-5.4-mini",
    async_client=AsyncOpenAI(
        api_key=os.environ["LOGFIRE_GATEWAY_API_KEY"],
        base_url="https://gateway-us.pydantic.dev/proxy/openai",
    ),
)


async def main() -> None:
    history = ChatHistory()
    history.add_user_message("What is the weather in London?")
    response = await chat_completion.get_chat_message_content(
        chat_history=history,
        settings=OpenAIChatPromptExecutionSettings(),
    )
    print(response)


if __name__ == "__main__":
    asyncio.run(main())
```

## .NET {#dotnet}

```csharp title="semantic-kernel-gateway.cs" skip-run="true" skip-reason="external-connection"
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
