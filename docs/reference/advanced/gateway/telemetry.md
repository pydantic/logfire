---
title: "See Gateway requests in your app's trace"
description: "Send trace context and baggage from your app to the AI Gateway, so Gateway spans join your trace and carry your attributes."
---

# See Gateway requests in your app's trace

See each model call as one step in the trace of the request that triggered it. Your app's spans and the Gateway's span share one trace, and one query can filter both by the same attributes.

A **span** is one unit of work, with a name, a start, and a duration. A **trace** is the full journey of one request, made of nested spans. With [Gateway telemetry](index.md#telemetry) enabled, the Gateway records every request as a span in your Logfire project, with the model, token counts, cost, and timing. This page shows how to make that span a child of a span in your app, and how to copy your own attributes onto it.

Skip this page if you only need the Gateway's own spans. Gateway telemetry works with no change in your app. Without trace headers, each Gateway span starts a trace of its own.

## Prerequisites

- Gateway telemetry enabled for a project. Open **Gateway → Settings**, find the **Telemetry** card, and select the project. The recommended setup in [Send your first Gateway request](first-request.md) does this for you.
- A Gateway API key for that project. Open **Gateway → Connect** to copy one. The Gateway writes its spans to the project that the key belongs to.
- A write token (the credential your app uses to send data to a Logfire project) for the same project, so your app's spans reach the project that holds the Gateway's spans. Create one under **Project → Settings → Write tokens**. See [Create write tokens](../../../how-to-guides/create-write-tokens.md).

!!! note "Baggage is stored in your project"
    Baggage is small key/value data that rides along with a request. The Gateway saves every baggage entry as an attribute on its span, and it also records the whole `baggage` header as the `http.request.header.baggage` attribute. Everyone with access to the project can read both. The Gateway does not send baggage to the model provider. Its guardrails check prompts and responses, not baggage. Do not put secrets or personal data in baggage.

## Send trace context and baggage from your app

The Gateway reads `traceparent`, `baggage`, and, when present, `tracestate`. The `traceparent` header names the span in your app that the Gateway's span continues. The optional `tracestate` header carries extra vendor data alongside it. All three use the format that the World Wide Web Consortium (W3C) defines for OpenTelemetry, the open standard for collecting traces, metrics, and logs. Your app needs to send `traceparent` and `baggage`. How depends on the SDK that calls the Gateway.

### With Pydantic AI

The `gateway/` model provider in Pydantic AI adds both headers for you whenever your app has an active trace. Install the packages, and export your write token:

```bash
pip install logfire pydantic-ai
export LOGFIRE_TOKEN='<YOUR_WRITE_TOKEN>'
```

Then run this script. It sends the model call to the Gateway: the `gateway/` prefix in the model name selects the Gateway provider, and the two `PYDANTIC_AI_GATEWAY_*` variables hold your API key and the Gateway URL. Use the base URL that **Gateway → Connect** shows for your region.

```python skip-run="true" skip-reason="external-connection"
import os

from pydantic_ai import Agent

import logfire

os.environ['PYDANTIC_AI_GATEWAY_API_KEY'] = '<YOUR_GATEWAY_API_KEY>'
os.environ['PYDANTIC_AI_GATEWAY_BASE_URL'] = 'https://gateway-us.pydantic.dev/proxy'

logfire.configure(service_name='gateway-demo')
logfire.instrument_pydantic_ai()

agent = Agent('gateway/openai:gpt-5.2', instructions='say only hi')

with logfire.set_baggage(user_tier='pro', experiment='ranking-v2'):
    result = agent.run_sync('hi')

print(repr(result.output))
```

Pydantic AI also puts its own entries in baggage: `gen_ai.agent.name`, `gen_ai.agent.call.id`, and `gen_ai.conversation.id`. The Gateway copies them onto its span next to `user_tier` and `experiment`.

### With another SDK

Other SDKs, such as the OpenAI SDK, send no trace headers on their own. Instrument the HTTP client that the SDK uses, and the Logfire SDK adds both headers to every request. The OpenAI SDK uses `httpx`:

```bash
pip install "logfire[httpx]" openai
```

```python skip-run="true" skip-reason="external-connection"
from openai import OpenAI

import logfire

logfire.configure(service_name='gateway-demo')
logfire.instrument_httpx()  # adds the traceparent and baggage headers

client = OpenAI(
    api_key='<YOUR_GATEWAY_API_KEY>',
    base_url='https://gateway-us.pydantic.dev/proxy/openai',
)

with logfire.span('handle request'), logfire.set_baggage(user_tier='pro'):
    response = client.chat.completions.create(
        model='gpt-5.2',
        messages=[{'role': 'user', 'content': 'Say only hi'}],
    )

print(response.choices[0].message.content)
```

Without the `instrument_httpx` line, the Gateway receives no trace context and starts a trace of its own.

Any HTTP client that sends the two headers works the same way, including one that you instrument with another OpenTelemetry SDK or one where you set the headers by hand:

```text
traceparent: 00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01
baggage: user_tier=pro,experiment=ranking-v2
```

See [Baggage](../baggage.md) for how `set_baggage` works, and [Distributed tracing](../../../how-to-guides/distributed-tracing.md) for context propagation across services.

## Verify

Open the project in **Live View**. You should see one trace in which the Gateway's span is nested under a span from your app. Span names depend on the SDK versions, but the nesting looks like this. With Pydantic AI:

```text
invoke_agent agent
└─ chat gpt-5.2        (Pydantic AI: the model request)
   └─ chat gpt-5.2     (Gateway: model, token counts, cost)
```

With the OpenAI SDK and `instrument_httpx`:

```text
handle request
└─ POST                (httpx: the HTTP call)
   └─ chat gpt-5.2     (Gateway: model, token counts, cost)
```

Then query for the baggage. The same filter returns your app's spans and the Gateway's span:

```sql
SELECT start_timestamp, span_name, trace_id, attributes
FROM records
WHERE attributes->>'user_tier' = 'pro'
```

## What the Gateway does with each header

| Header | Gateway telemetry (your project) | Model provider |
| --- | --- | --- |
| `traceparent`, `tracestate` | The Gateway's span becomes a child of your span, in the same trace. | The provider receives one valid `traceparent` that continues your trace. |
| `baggage` | Each entry becomes an attribute on the Gateway's span, under the key you sent. The whole header is also recorded as `http.request.header.baggage`. | Not sent. |

These rules apply to baggage entries:

- **Gateway attributes win.** If an entry has the same key as an attribute that the Gateway sets itself, such as `gen_ai.request.model`, the Gateway keeps its own value.
- **Size limits.** The Gateway reads at most 8,192 bytes of baggage, and at most 4,096 bytes for one entry. It ignores entries beyond those limits.
- **Message capture.** When **Include messages** is off for the project, the Gateway leaves prompts and responses out of its span. It also does not copy baggage entries whose keys match those message attributes. The setting filters by key. It does not inspect values, and it does not remove the `http.request.header.baggage` attribute. Keep prompt text out of baggage.

## Troubleshooting

- **The Gateway span is in a separate trace.** The request carried no `traceparent`. With the OpenAI SDK or another SDK, check that `logfire.instrument_httpx()` runs before the first model call. With Pydantic AI, check that you call `logfire.configure()` and `logfire.instrument_pydantic_ai()` first, so an active trace exists. In both cases, check that no proxy between your app and the Gateway removes headers.
- **The Gateway span has no baggage attributes.** The request carried no `baggage` header. Make the model call inside the `set_baggage` block, and check that the entry is under the size limits above.
- **There is no Gateway span.** Gateway telemetry is not enabled for the project that owns your API key. See "No trace" in [Send your first Gateway request](first-request.md).
- **Your app's spans are in another project.** The `LOGFIRE_TOKEN` belongs to a different project than the Gateway API key. Use a write token from the same project.

## Next steps

- Choose what the Gateway records: [Protect request data](protect-data.md).
- Cap what a key or a project can spend: [Control AI Gateway spending](spending-policies.md).
- Learn how baggage works in the SDK: [Baggage](../baggage.md).
