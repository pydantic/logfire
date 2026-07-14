---
title: "Connect frameworks to the AI Gateway"
description: "Use the Logfire AI Gateway with agent frameworks and model SDKs."
---

# Connect frameworks to the AI Gateway

Keep the framework, prompts, tools, and agent workflow you already use while Logfire tracks model usage and applies gateway spending limits.

Each guide shows the two client settings you need to change: the API key and gateway URL. You can point them at one model provider, or at a routing group that tries another provider if the first one fails.

## Before you start

1. If your organization has not enabled the gateway, follow [Enable the gateway](/logfire/manage/ai-gateway/#enable-the-gateway). You need to be an organization admin.
2. In Logfire, open your organization, then select **AI Engineering** > **Gateway** > **API Keys**.
3. Create or copy a gateway API key, then set it in the terminal where you will run the example:

    ```bash
    export LOGFIRE_GATEWAY_API_KEY="..."
    ```

4. On the Gateway **Connect** tab, select a provider and model. Copy the gateway URL and model name into the example.

The examples use the United States OpenAI-compatible route, `https://gateway-us.pydantic.dev/proxy/openai`. For an organization in the European Union, use `gateway-eu` instead. For a self-hosted organization, copy the URL from the **Connect** tab.

Most examples use an OpenAI-compatible client. The provider or routing group you select must support the OpenAI request format and the model name in the example. Provider-native APIs, such as Anthropic Messages, require that provider's client. See [Connect an SDK](/logfire/manage/ai-gateway/#connect-an-sdk) for both patterns.

!!! note "Model data passes through Logfire"
    These settings send prompts, tool inputs, and model responses through the Logfire AI Gateway and the selected model provider. If gateway telemetry is enabled, Logfire records the model, latency, token usage, and conversation content in your selected project. Calls to built-in providers count toward your gateway spend.

## Choose your framework

| Framework or SDK | Languages |
| --- | --- |
| Agno | [Python](agno.md) |
| Genkit | [Go](genkit.md#go), [TypeScript](genkit.md#typescript) |
| Google ADK | [Go](google-adk.md#go), [Python](google-adk.md#python) |
| Haystack | [Python](haystack.md) |
| Instructor | [Python](instructor.md) |
| LangChain | [TypeScript](langchain.md#typescript), [Python](langchain.md#python) |
| LlamaIndex | [Python](llamaindex.md) |
| Mastra | [TypeScript](mastra.md) |
| Microsoft Agent Framework | [.NET](microsoft-agent-framework.md#dotnet), [Python](microsoft-agent-framework.md#python) |
| OpenAI Agents SDK | [TypeScript](openai-agents-sdk.md#typescript), [Python](openai-agents-sdk.md#python) |
| OpenAI SDK | [.NET](openai-sdk.md#dotnet), [Go](openai-sdk.md#go), [TypeScript](openai-sdk.md#typescript), [Python](openai-sdk.md#python) |
| Semantic Kernel | [.NET](semantic-kernel.md#dotnet), [Python](semantic-kernel.md#python) |
| Smolagents | [Python](smolagents.md) |
| Strands Agents | [TypeScript](strands-agents.md#typescript), [Python](strands-agents.md#python) |
| Vercel AI SDK | [TypeScript](vercel-ai-sdk.md) |
| VoltAgent | [TypeScript](voltagent.md) |

## Next steps

Read the [AI Gateway overview](/logfire/manage/ai-gateway/) to learn how providers, routing groups, spending limits, and telemetry work together.
