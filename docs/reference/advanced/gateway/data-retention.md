---
title: "Control what the AI Gateway stores"
description: "What the AI Gateway stores for each request and for how long, how to turn off message capture and response caching, and how provider zero data retention settings pass through."
---

# Control what the AI Gateway stores

Know where the content of a Gateway request can persist, for how long, and which switch removes it. This page lists every store, shows how to turn off message capture and response caching, and states what the Gateway does with each provider's retention settings.

Two terms appear throughout:

- A **built-in provider** uses a credential that Pydantic owns and shares across organizations. A **custom provider** uses your own provider account. See [Add your own provider](byok-providers.md).
- **Zero data retention (ZDR)** means the model provider does not keep your prompts or responses after it answers the request.

## What the Gateway stores

The Gateway holds request and response bodies in memory while it proxies them. It does not write them to disk. These are the places where data persists after the request ends.

| Data | Contains prompts or responses | Where | How long | How to turn it off |
| --- | --- | --- | --- | --- |
| Request spans: model, token counts, cost, status, timing, URL, request and response headers | No. The URL, [baggage](telemetry.md), and every header except the [credential headers](#turn-off-message-capture) are recorded as you sent them. | Your Logfire project | Your organization's retention period. The default is 30 days. | No setting turns it off. See [Request spans have no off switch](#request-spans-have-no-off-switch). |
| Message content on those spans: prompts, responses, system instructions, stop sequences, and raw HTTP bodies | Yes | Your Logfire project | Your organization's retention period | Turn off **Include messages** for the project. It is on by default. |
| Response cache entries | Yes. The entry holds the response body. The request is only hashed into the cache key. | The Gateway's cache | 24 hours | Off by default. You turn it on for each API key. Send `Cache-Control: no-store` to skip it for one request. |
| Spend totals for each key, member, project, and organization | No. Amounts in US dollars only. | The Gateway's database | No fixed expiry | You cannot turn it off. [Spending limits](spending-policies.md) need it. |
| Built-in provider usage: cost and request count for each key | No | The Gateway's database | Hourly rows for three months. Monthly totals have no fixed expiry. | You cannot turn it off. Billing needs it. |
| Provider block events: key ID, provider type, and a fixed reason code | No | The Gateway's database | Until you delete the API key | You cannot turn it off. |

A **span** is one unit of work, with a name, a start, and a duration. The Gateway records one span for each attempt to reach a provider.

The Gateway does not store the raw payload for these features:

- **Files and batches.** The Gateway refuses these endpoints on a built-in provider, because the files of every organization would share one provider account. On a custom provider, the Gateway forwards the request unchanged, and the file or batch lives only in your provider account. The provider's retention rules apply.
- **Realtime sessions.** The Gateway relays audio and text frames and reads token usage from them. It records usage and cost. It does not record frames or transcripts.
- **Audio uploads.** A span for a transcription request records the file name and size, not the audio. The transcript text counts as message content.
- **Guardrail matches.** [Guardrails](protect-data.md) record which protection ran, its action, and the number of matches. They do not record the matched text.

!!! warning "A Presidio protection sends prompt text to your Presidio service"
    A Presidio protection sends the prompt text to the base URL of the connection that you configured. What that service stores is outside the Gateway.

### Request spans have no off switch

The Gateway writes its spans to the project that owns the API key. No setting stops that export, because usage, cost, and spending limits are only auditable when every request leaves a record. **Include messages** decides whether those spans also carry content.

There is one exception. The Gateway honors the sampling decision in a `traceparent` header. If your app marks its trace as not sampled, the Gateway exports no span for that request.

Your organization's retention period decides how long the spans live. The default is 30 days. Growth organizations can set up to 90 days, and Enterprise organizations can set a longer period.

## Turn off message capture

Message capture is a project setting. It is on by default, so a new project shows you the prompts and responses behind each cost without extra setup.

You need permission to change project settings.

1. Open [**AI Engineering → Gateway**](https://logfire.pydantic.dev/-/redirect/default-org/-/gateway) and select the **Settings** tab.
2. In the **Telemetry** card, select the project.
3. Turn off **Include messages**.

The setting applies to every API key in that project. It can take up to 60 seconds to reach requests in flight.

With **Include messages** off, the Gateway removes these attributes from each span before it exports the span:

| Removed | Kept |
| --- | --- |
| `gen_ai.input.messages` | Model, token counts, cost, status, and timing |
| `gen_ai.output.messages` | Request and response headers, except credentials |
| `gen_ai.system_instructions` | `url.full` |
| `gen_ai.request.stop_sequences` | Baggage entries under other keys |
| `http.request.body.text` and `http.response.body.text` | `http.request.body.size` |
| The text of `error` and `error.message` | Guardrail and optimization metadata |

!!! warning "Existing spans keep their messages"
    Turning off **Include messages** affects new requests only. Spans that the Gateway already wrote keep their content until your retention period removes them.

!!! warning "Headers and baggage are not message content"
    The setting removes attributes by name. It does not inspect values. A prompt that you put in a header, a query string, or a baggage entry stays on the span. The Gateway never records the `Authorization`, `Cookie`, `Proxy-Authorization`, `X-API-Key`, and `X-Goog-Api-Key` headers.

### Check that capture is off

Send a request with a key from that project, then run this query in the project's **Explore** view:

```sql
SELECT
    start_timestamp,
    span_name,
    attributes->>'gen_ai.input.messages' AS input_messages
FROM records
WHERE otel_scope_name = 'pydantic-ai-gateway'
ORDER BY start_timestamp DESC
LIMIT 5
```

The newest rows have an empty `input_messages` column.

## Turn off response caching

The response cache answers a repeated, identical, non-streaming request from a stored copy of the first response. It is off by default, because a cache entry is a copy of a model response that outlives the request. You opt in for each API key.

The cache has these limits:

| Property | Value |
| --- | --- |
| Scope | One API key. A key never reads the entry of another key. |
| Requests | Chat Completions, Responses, and Anthropic Messages. Non-streaming only. |
| Stored | The response body of a successful response, up to 256 KiB. The request body is hashed, not stored. |
| Lifetime | 24 hours. Entries expire. You cannot purge them earlier. |

### For an API key

1. Open [**AI Engineering → Gateway**](https://logfire.pydantic.dev/-/redirect/default-org/-/gateway) and select the **API Keys** tab.
2. Open the key and edit it.
3. Set **Response caching** to **Disabled**.

**Default** also means off today. Choose **Disabled** when the key must stay uncached even if the default changes.

The Gateway stops reading and writing the cache for that key. Entries that the key already stored are no longer served, and they expire within 24 hours.

### For one request

Send `Cache-Control: no-store`. The Gateway neither reads nor writes the cache for that request, even when the key has caching on.

```python skip-run="true" skip-reason="external-connection"
from openai import OpenAI

client = OpenAI(
    api_key='<YOUR_GATEWAY_API_KEY>',
    base_url='https://gateway-us.pydantic.dev/proxy/openai',
)

response = client.chat.completions.with_raw_response.create(
    model='gpt-5.2',
    messages=[{'role': 'user', 'content': 'Say only hi'}],
    extra_headers={'Cache-Control': 'no-store'},
)

print(response.headers.get('x-cache-status'))
#> BYPASS
print(response.parse().choices[0].message.content)
#> hi
```

Copy the API key and the base URL for your region from **Gateway → Connect**. This output is for a key with **Response caching** set to **Enabled**. For any other key the header is absent and the first line prints `None`.

The `X-Cache-Status` response header reports what the cache did:

| Value | Meaning |
| --- | --- |
| `HIT` | The Gateway answered from the cache. The provider did not receive the request. |
| `MISS` | The Gateway called the provider and stored the response. |
| `BYPASS` | The Gateway called the provider and did not read the cache. |
| Header absent | Caching is off for the key, or the request is not cacheable. |

`Cache-Control: no-cache` skips the read but still stores the new response. Use `no-store` when the response must not persist.

!!! note "The response cache is separate from provider prompt caching"
    Provider prompt caching, such as Anthropic `cache_control` or OpenAI `prompt_cache_key`, happens in the provider's account. The Gateway forwards those fields unchanged and stores nothing for them.

## Provider zero data retention

The settings above control what the Gateway stores. They do not control what the model provider stores. Two things decide that: the retention terms of the provider account, and the retention fields in your request.

| Provider kind | Whose account | Who sets the retention terms |
| --- | --- | --- |
| Custom provider | Yours | You, in your agreement with the provider. The Gateway does not change it. |
| Built-in provider | Pydantic's | Pydantic. A built-in provider is ZDR only after Pydantic confirms it for that provider account. |

Pydantic has confirmed these built-in providers as ZDR:

| Built-in provider | ZDR |
| --- | --- |
| Google Vertex AI | Yes |
| Groq | Yes |
| Every other built-in provider | Not confirmed |

You can use the ZDR built-in providers on every plan. Send your request to a route whose only built-in providers are ZDR. A [Gateway endpoint](endpoints.md) that also includes another built-in provider can share traffic with it or fail over to it, so that route does not guarantee ZDR.

Only [enforcing ZDR](#require-zero-data-retention-for-built-in-providers), so that a request cannot reach any other built-in provider, needs an Enterprise Cloud organization or a self-hosted deployment.

### How request fields pass through

The Gateway sends your request body to the provider with only the changes listed below. It never adds, removes, or changes a retention field. If you leave a field out, the provider applies its own default.

| Provider | Forwarded unchanged | Changed by the Gateway |
| --- | --- | --- |
| OpenAI, Azure OpenAI | `store`, `previous_response_id`, `metadata`, `prompt_cache_key`, `prompt_cache_retention`, `user` | `safety_identifier`: the Gateway puts an identifier for your organization in front of your value. Streaming Chat Completions: the Gateway sets `stream_options.include_usage` to `true`. |
| Anthropic | `cache_control`, the `anthropic-beta` and `anthropic-version` headers, other `metadata` keys | `metadata.user_id`: the Gateway puts an identifier for your organization in front of your value. |
| Google Vertex AI, Google AI Studio | The whole `generateContent` body, including `cachedContent` | Nothing |
| AWS Bedrock | The whole Converse body | Nothing |
| Groq, and custom OpenAI-compatible or Anthropic-compatible providers | The whole body | Nothing |
| Mistral | The whole body | Streaming chat: the Gateway sets `stream_options.include_usage` to `true`. |

The Gateway changes `safety_identifier` and `metadata.user_id` because those are the fields that providers use to attribute abuse. On a shared built-in credential, the organization identifier lets the provider act on one organization and not on every organization that uses the credential. The identifier is derived from your organization ID. It contains no prompt content.

The Gateway forces `include_usage` on streams because it reads token usage from the stream to record cost and enforce spending limits.

The Gateway forwards your request headers, except these:

| Not forwarded | Why |
| --- | --- |
| `Authorization`, `X-API-Key`, `X-Goog-Api-Key` | They hold your Gateway API key. The Gateway attaches the provider credential in their place. |
| `Cookie`, `Origin`, `Referer`, `Forwarded`, `Via`, `X-Real-IP`, and headers that start with `X-Forwarded-` | They identify the caller. No provider needs them. |
| `baggage`, and headers that start with `X-Pydantic-`, `X-Gateway-`, or `X-Routing-` | They address the Gateway. |

The Gateway appends its own name to `User-Agent`.

### Ask OpenAI not to store a response

The OpenAI Responses API stores each response in the provider account unless the request says otherwise. Set `store=False`, and the Gateway forwards it:

```python skip-run="true" skip-reason="external-connection"
from openai import OpenAI

client = OpenAI(
    api_key='<YOUR_GATEWAY_API_KEY>',
    base_url='https://gateway-us.pydantic.dev/proxy/openai',
)

response = client.responses.create(
    model='gpt-5.2',
    input='Say only hi',
    store=False,
)

print(response.output_text)
#> hi
```

!!! note "Stored provider objects need a custom provider"
    Endpoints that read or delete stored provider objects, such as a stored response, a file, a batch, or Vertex AI cached content, are refused on a built-in provider. On a custom provider the Gateway forwards them to your account.

### Require zero data retention for built-in providers

!!! note "Experimental"
    The zero data retention requirement is experimental, and it can change. The organization setting needs an Enterprise Cloud organization or a self-hosted deployment.

Among built-in providers, a request that requires ZDR can only reach one that Pydantic confirmed as ZDR. Custom providers are not affected, because their retention terms are yours.

Send the `x-pydantic-zero-data-retention` header to require ZDR for one request or one client:

```python skip-run="true" skip-reason="external-connection"
from openai import OpenAI

client = OpenAI(
    api_key='<YOUR_GATEWAY_API_KEY>',
    base_url='https://gateway-us.pydantic.dev/proxy/openai',
    default_headers={'x-pydantic-zero-data-retention': 'true'},
)

response = client.chat.completions.create(
    model='gpt-5.2',
    messages=[{'role': 'user', 'content': 'Say only hi'}],
)

print(response.choices[0].message.content)
#> hi
```

To require ZDR for every request in the organization, open **Gateway → Settings**, find the **Zero data retention** card, and turn on **Require for the whole organization**.

These rules apply:

| Case | Result |
| --- | --- |
| The route has a ZDR built-in provider or a custom provider | The request goes to that provider. |
| Every provider of the route is a built-in provider that is not ZDR | `403` with `error_code: zero_data_retention_required`. The provider receives nothing. |
| The header value is not `true` or `false` | `400` with `error_code: zero_data_retention_header_invalid`. A typo never sends data to a provider that retains it. |
| The organization requires ZDR and the header is `false` | ZDR is still required. The header can add the requirement. It cannot remove it. |

The Gateway removes the header before it forwards the request. Realtime sessions follow the same rules.

!!! warning "The requirement only selects providers"
    Requiring ZDR does not change what the Gateway stores. To keep prompts and responses out of Logfire too, [turn off message capture](#turn-off-message-capture) and leave [response caching](#turn-off-response-caching) off.

## Troubleshooting

- **A span still shows prompts after you turned off Include messages.** The span is older than the change, or the request used a key from another project. The setting is per project. Check the **Telemetry** card for the project that owns the key.
- **`X-Cache-Status` is `HIT` on a request that must not be cached.** The key has **Response caching** set to **Enabled**. Send `Cache-Control: no-store` on that request, or set the key to **Disabled**.
- **A request returns `403` with `zero_data_retention_required`.** No provider of that route is confirmed as ZDR. Use a route with a custom provider, or remove the requirement.
- **A request to a files or batches endpoint returns `404`.** The route uses a built-in provider. [Add your own provider](byok-providers.md) and send the request through it.

## Next steps

- Detect and redact secrets before a request leaves the Gateway: [Protect Gateway requests](protect-data.md).
- Use your own provider account and its retention terms: [Add your own provider](byok-providers.md).
- Choose which attributes ride on Gateway spans: [See Gateway requests in your app's trace](telemetry.md).
