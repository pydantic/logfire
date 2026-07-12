---
title: "Embeddings"
description: "Discover and call embedding models through the Logfire AI Gateway with OpenAI-compatible embeddings requests."
---

# Embeddings

The AI Gateway proxies embedding requests the same way it proxies chat: point an OpenAI-compatible client at a gateway route and call its `/embeddings` endpoint. Embedding models are discovered per route, listed separately from chat models in the **Connect** tab, and traced like any other gateway request. Usage is recorded for every embeddings call; estimated cost is tracked when pricing data is available for the model, and where the charge lands depends on the provider type — built-in provider usage draws from your prepaid gateway balance, while bring-your-own-key (BYOK) usage is billed directly by the upstream provider (see [Providers](index.md#providers)).

## Which providers can serve embeddings

Embeddings are available for provider types whose `/embeddings` endpoint the gateway proxies as an OpenAI-compatible request: **OpenAI**, **Azure Foundry**, **OVHcloud**, **Doubleword**, **Ollama**, and **custom** OpenAI-compatible providers. These carry an **Embeddings** badge on the **Providers** tab.

Anthropic and Google Vertex AI don't expose an OpenAI-compatible embeddings API, so they're chat-only and show no badge.

The badge means the provider *can* serve embeddings; which embedding models are actually available depends on what the provider advertises (see below).

## Discovering a route's embedding models

Each route reports its chat and embedding models separately. List them with `GET /proxy/models`.

The requests on this page need two values. Create or reveal a gateway API key on the **API Keys** tab and use it in place of `<YOUR_GATEWAY_API_KEY>`; for the route, use a provider slug from the **Providers** tab (or a routing group slug from **Routing**) — the examples below use `openai`.

```bash
curl "https://gateway-us.pydantic.dev/proxy/models?route=openai" \
  -H "Authorization: Bearer <YOUR_GATEWAY_API_KEY>"
```

The response is one entry per route, with chat models under `models` and embedding models split out under `embedding_models`:

```json
[
  {
    "route": "openai",
    "provider": "openai",
    "models": [{ "id": "gpt-5.2", "name": "gpt-5.2", "context_window": 400000 }],
    "embedding_models": [
      { "id": "text-embedding-3-small", "name": "text-embedding-3-small", "context_window": 8192 },
      { "id": "text-embedding-3-large", "name": "text-embedding-3-large", "context_window": 8192 }
    ]
  }
]
```

In the **Connect** tab, the model picker groups these into **Chat models** and **Embedding models**, and selecting an embedding model switches the generated snippets to embeddings requests. If a provider advertises no embedding models, the picker stays a flat list with no split. (Google Vertex AI doesn't support model listing, so its Connect tab shows a free-text model box instead.)

## Sending an embeddings request

Address the request to `<gateway-base-url>/<route>/embeddings` with an OpenAI-compatible body: a `model` and an `input` that is either a string or a list of strings. The response is the standard OpenAI shape — a `data` array with one `embedding` (a list of floats) per input — so you can embed several inputs in one request.

The examples below use the `openai` route in the US region; see the [gateway base URLs](index.md#connect-an-sdk) for other regions.

=== "curl"

    ```bash
    curl https://gateway-us.pydantic.dev/proxy/openai/embeddings \
      -H "Authorization: Bearer <YOUR_GATEWAY_API_KEY>" \
      -H "Content-Type: application/json" \
      -d '{
        "model": "text-embedding-3-small",
        "input": "The quick brown fox jumps over the lazy dog."
      }'
    ```

=== "Python (OpenAI SDK)"

    ```python skip-run="true" skip-reason="external-connection"
    from openai import OpenAI

    client = OpenAI(
        api_key='<YOUR_GATEWAY_API_KEY>',
        base_url='https://gateway-us.pydantic.dev/proxy/openai',
    )

    response = client.embeddings.create(
        model='text-embedding-3-small',
        input='The quick brown fox jumps over the lazy dog.',
    )
    print(response.data[0].embedding[:8])
    ```

=== "TypeScript (OpenAI SDK)"

    ```typescript
    import OpenAI from 'openai'

    const client = new OpenAI({
      apiKey: '<YOUR_GATEWAY_API_KEY>',
      baseURL: 'https://gateway-us.pydantic.dev/proxy/openai',
    })

    const response = await client.embeddings.create({
      model: 'text-embedding-3-small',
      input: 'The quick brown fox jumps over the lazy dog.',
    })
    console.log(response.data[0].embedding.slice(0, 8))
    ```

=== "Pydantic AI"

    ```python skip-run="true" skip-reason="external-connection"
    import asyncio
    import os

    from pydantic_ai import Embedder

    os.environ['PYDANTIC_AI_GATEWAY_API_KEY'] = '<YOUR_GATEWAY_API_KEY>'
    os.environ['PYDANTIC_AI_GATEWAY_BASE_URL'] = 'https://gateway-us.pydantic.dev/proxy'

    embedder = Embedder('gateway/openai:text-embedding-3-small')


    async def main() -> None:
        result = await embedder.embed_documents(['The quick brown fox jumps over the lazy dog.'])
        print(result.embeddings[0][:8])


    asyncio.run(main())
    ```

Usage is recorded on every embeddings request like any other gateway call — and estimated cost too, when pricing data is available for the model — so embeddings show up in your **Spending** analytics and (when telemetry is enabled) as traces alongside the rest of your LLM traffic. As with chat, built-in provider usage draws from your prepaid gateway balance while BYOK usage is billed by the upstream provider.

## See also

- [AI Gateway](index.md) — enabling the gateway, providers, routing, and connecting SDKs.
