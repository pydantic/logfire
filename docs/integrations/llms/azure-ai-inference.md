---
title: Pydantic Logfire Azure AI Inference Integration
description: "Instrument calls to Azure AI Inference with logfire.instrument_azure_ai_inference(). Track chat completions, embeddings, streaming responses, and token usage."
integration: logfire
---
# Azure AI Inference

**Logfire** supports instrumenting calls to [Azure AI Inference](https://pypi.org/project/azure-ai-inference/) with the [`logfire.instrument_azure_ai_inference()`][logfire.Logfire.instrument_azure_ai_inference] method.

```python hl_lines="11-12" skip-run="true" skip-reason="external-connection"
from azure.ai.inference import ChatCompletionsClient
from azure.core.credentials import AzureKeyCredential

import logfire

client = ChatCompletionsClient(
    endpoint='https://my-endpoint.inference.ai.azure.com',
    credential=AzureKeyCredential('my-api-key'),
)

logfire.configure()
logfire.instrument_azure_ai_inference(client)

response = client.complete(
    model='gpt-4',
    messages=[
        {'role': 'system', 'content': 'You are a helpful assistant.'},
        {'role': 'user', 'content': 'Please write me a limerick about Python logging.'},
    ],
)
print(response.choices[0].message.content)
```

With that you get:

* a span around the call which records duration and captures any exceptions that might occur
* Human-readable display of the conversation with the agent
* details of the response, including the number of tokens used

## Installation

Install Logfire with the `azure-ai-inference` extra:

{{ install_logfire(extras=['azure-ai-inference']) }}

## Methods covered

The following methods are covered:

- [`ChatCompletionsClient.complete`](https://learn.microsoft.com/python/api/azure-ai-inference/azure.ai.inference.chatcompletionsclient) - with and without `stream=True`
- [`EmbeddingsClient.embed`](https://learn.microsoft.com/python/api/azure-ai-inference/azure.ai.inference.embeddingsclient)

All methods are covered with both sync (`azure.ai.inference`) and async (`azure.ai.inference.aio`) clients.

## Streaming Responses

When instrumenting streaming responses, Logfire creates two spans - one around the initial request and one around the streamed response.

```python skip-run="true" skip-reason="external-connection"
from azure.ai.inference import ChatCompletionsClient
from azure.core.credentials import AzureKeyCredential

import logfire

client = ChatCompletionsClient(
    endpoint='https://my-endpoint.inference.ai.azure.com',
    credential=AzureKeyCredential('my-api-key'),
)

logfire.configure()
logfire.instrument_azure_ai_inference(client)

response = client.complete(
    model='gpt-4',
    messages=[{'role': 'user', 'content': 'Write Python to show a tree of files.'}],
    stream=True,
)
for chunk in response:
    if chunk.choices:
        delta = chunk.choices[0].delta
        if delta and delta.content:
            print(delta.content, end='', flush=True)
```

## Embeddings

You can also instrument the `EmbeddingsClient`:

```python skip-run="true" skip-reason="external-connection"
from azure.ai.inference import EmbeddingsClient
from azure.core.credentials import AzureKeyCredential

import logfire

client = EmbeddingsClient(
    endpoint='https://my-endpoint.inference.ai.azure.com',
    credential=AzureKeyCredential('my-api-key'),
)

logfire.configure()
logfire.instrument_azure_ai_inference(client)

response = client.embed(
    model='text-embedding-ada-002',
    input=['Hello world'],
)
print(len(response.data[0].embedding))
```

## Async Support

Async clients from `azure.ai.inference.aio` are fully supported:

```python skip-run="true" skip-reason="external-connection"
from azure.ai.inference.aio import ChatCompletionsClient
from azure.core.credentials import AzureKeyCredential

import logfire

client = ChatCompletionsClient(
    endpoint='https://my-endpoint.inference.ai.azure.com',
    credential=AzureKeyCredential('my-api-key'),
)

logfire.configure()
logfire.instrument_azure_ai_inference(client)
```

## Global Instrumentation

If no client is passed, all `ChatCompletionsClient` and `EmbeddingsClient` classes (both sync and async) are instrumented:

```python skip-run="true" skip-reason="external-connection"
import logfire

logfire.configure()
logfire.instrument_azure_ai_inference()
```
