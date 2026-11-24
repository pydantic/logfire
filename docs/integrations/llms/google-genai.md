---
title: "Instrument Google Gen AI: see every Gemini call your app makes"
description: "Add a few lines to your Google Gen AI code and see every Gemini model call in Logfire: the full conversation, token usage, duration, and any errors."
integration: logfire
---
# Google Gen AI SDK

See every call your app makes to Google's Gemini models through the
[Google Gen AI SDK (`google-genai`)](https://googleapis.github.io/python-genai/): the full
conversation, how many **tokens** (the units a model reads and bills by, a few characters of text
each) it used, how long it took, and any errors, as a **trace** (the full journey of one request or agent run,
made of nested **spans**, where each span is one unit of work with a name, a start, and a duration)
in Logfire.

## What you'll capture

- Each model call as a span, with its duration and any exceptions
- The full conversation between your app and the model
- Response details, including the number of tokens used

{{ before_you_start() }}

You'll also need a **Google Gemini API key**, from [Google AI Studio](https://aistudio.google.com/apikey). The Google Gen AI SDK reads it from the `GEMINI_API_KEY` (or `GOOGLE_API_KEY`) environment variable.

## Installation

Install `logfire` with the `google-genai` extra:

{{ install_logfire(extras=['google-genai']) }}

The extra installs `opentelemetry-instrumentation-google-genai`, the OpenTelemetry package that
records Google Gen AI calls. Version `1.3b0` supports `google-genai>=1.32.0,<3`; it does not support
Google Gen AI SDK 3.x. Use a Google Gen AI SDK version supported by the installed OpenTelemetry
package.

To capture costs reported by the [AI Gateway](../../reference/advanced/gateway/index.md) for streamed
responses, you also need `google-genai>=1.69.0`, within that supported range. Earlier SDK versions
do not expose the `part_metadata` field that carries those costs. This requirement concerns
gateway-reported costs, separate from [token-based cost estimates](../../cookbook/track-llm-cost.md).

## Usage

Add two lines to your app: `logfire.configure()` to connect to your project, and
[`logfire.instrument_google_genai()`][logfire.Logfire.instrument_google_genai] to record every
Gemini call.

By default, the prompts and completions are hidden: the spans show `<elided>` in their place. To
capture the actual message content (so you can read the conversation in Logfire), set the
`OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT` environment variable to `SPAN_ONLY`. This sends
the prompt and response text to Logfire, so leave it off if that content is sensitive. Logfire also
accepts the earlier values `true` and `false`, mapping them to `SPAN_ONLY` and `NO_CONTENT`. Other
instrumentors can interpret this OpenTelemetry environment variable differently; for Google Agent
Development Kit (ADK), see [its content-capture modes](./google-adk.md#usage).

```python hl_lines="8 10-11" skip-run="true" skip-reason="external-connection"
import os

from google.genai import Client

import logfire

# Set this to SPAN_ONLY to capture the actual prompts and completions in the spans.
os.environ['OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT'] = 'SPAN_ONLY'

logfire.configure()
logfire.instrument_google_genai()

client = Client()
response = client.models.generate_content(model='gemini-2.5-flash', contents=['Hi'])
print(response.text)
# Hello! How can I help you today?
```

This creates a span which shows the conversation in the Logfire UI:

<figure markdown="span">
![Logfire Google Gen AI conversation](../../images/logfire-screenshot-google-genai-llm-panel.png){ width="259" }
</figure>

## Verify it worked

Run your program, then open your project in the
[Logfire web app](https://logfire.pydantic.dev/) and go to the **Live** view. Within a few seconds you
should see a span for the Gemini call. Click it to read the conversation and see the token count and
duration.

## Troubleshooting

Not seeing your model calls in Logfire? Check these first:

- **Your Google Gen AI SDK version is supported.** If the OpenTelemetry package logs an error
  containing `falls outside of that range, so nothing can be instrumented`, it skips recording
  Google Gen AI calls. The calls can still succeed without creating spans. Use a supported SDK
  version as described under [Installation](#installation).
- **`logfire.configure()` runs before `logfire.instrument_google_genai()`.** Configure the connection
  first, then instrument.
- **You called `instrument_google_genai()` exactly once.**
- **Your Logfire write token is set.** In local development, install [uv](https://docs.astral.sh/uv/getting-started/installation/)
  if needed, then run `uvx logfire-cli auth` if needed, then
  `uvx logfire-cli init use` from your application's directory;
  in production, set the `LOGFIRE_TOKEN` environment variable. See [Getting Started](../../index.md).
- **Prompts and completions show as `<elided>`?** Set
  `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=SPAN_ONLY` before your app runs, as shown above.

## Reference

- API reference: [`logfire.instrument_google_genai()`][logfire.Logfire.instrument_google_genai]
- Underlying OpenTelemetry package:
  [`opentelemetry-instrumentation-google-genai`](https://pypi.org/project/opentelemetry-instrumentation-google-genai/)
