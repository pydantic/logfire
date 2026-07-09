---
title: "AI Gateway integrations"
description: "Connect frameworks and SDKs to the Logfire AI Gateway."
---

# AI Gateway integrations

These pages show how to point each framework or SDK at the Logfire AI Gateway so that all model calls flow through one place for usage tracking, spending limits, and provider fallback.

## Before you start

1. In Logfire, open your organization, then go to **AI Engineering** > **Gateway**.
2. Create or copy a gateway API key from the Gateway **API Keys** tab.
3. Set the key in your terminal:

    ```bash
    export LOGFIRE_GATEWAY_API_KEY="..."
    ```

Each example uses a gateway URL like `https://gateway-us.pydantic.dev/proxy/openai`, where the last part picks which model provider (OpenAI, Anthropic, Google, and so on) handles the call. To switch to a different provider — or to a routing group that combines several providers with fallback — copy the URL you want from the Gateway **Providers** or **Routing** tab.

## Examples

| Framework or SDK | Available in |
| --- | --- |
| Agno | [Python](/logfire/manage/ai-gateway/integrations/agno/) |
| Genkit | [Go](/logfire/manage/ai-gateway/integrations/genkit/#go), [JavaScript](/logfire/manage/ai-gateway/integrations/genkit/#javascript) |
| Google ADK | [Go](/logfire/manage/ai-gateway/integrations/google-adk/#go), [Python](/logfire/manage/ai-gateway/integrations/google-adk/#python) |
| Haystack | [Python](/logfire/manage/ai-gateway/integrations/haystack/) |
| Instructor | [Python](/logfire/manage/ai-gateway/integrations/instructor/) |
| LangChain | [TypeScript](/logfire/manage/ai-gateway/integrations/langchain/#typescript), [Python](/logfire/manage/ai-gateway/integrations/langchain/#python) |
| LlamaIndex | [Python](/logfire/manage/ai-gateway/integrations/llamaindex/) |
| Mastra | [JavaScript](/logfire/manage/ai-gateway/integrations/mastra/) |
| Microsoft Agent Framework | [.NET](/logfire/manage/ai-gateway/integrations/microsoft-agent-framework/#dotnet), [Python](/logfire/manage/ai-gateway/integrations/microsoft-agent-framework/#python) |
| OpenAI Agents SDK | [TypeScript](/logfire/manage/ai-gateway/integrations/openai-agents-sdk/#typescript), [Python](/logfire/manage/ai-gateway/integrations/openai-agents-sdk/#python) |
| OpenAI SDK | [.NET](/logfire/manage/ai-gateway/integrations/openai-sdk/#dotnet), [Go](/logfire/manage/ai-gateway/integrations/openai-sdk/#go), [TypeScript](/logfire/manage/ai-gateway/integrations/openai-sdk/#typescript), [Python](/logfire/manage/ai-gateway/integrations/openai-sdk/#python) |
| Semantic Kernel | [.NET](/logfire/manage/ai-gateway/integrations/semantic-kernel/#dotnet), [Python](/logfire/manage/ai-gateway/integrations/semantic-kernel/#python) |
| Smolagents | [Python](/logfire/manage/ai-gateway/integrations/smolagents/) |
| Strands Agents | [TypeScript](/logfire/manage/ai-gateway/integrations/strands-agents/#typescript), [Python](/logfire/manage/ai-gateway/integrations/strands-agents/#python) |
| Vercel AI SDK | [JavaScript](/logfire/manage/ai-gateway/integrations/vercel-ai-sdk/) |
| VoltAgent | [JavaScript](/logfire/manage/ai-gateway/integrations/voltagent/) |
