---
title: "Instrument OrcaRouter: see every model call your app makes"
description: "Add a few lines to your OpenAI-compatible OrcaRouter client and see every model call in Logfire: the full conversation, token usage, duration, and any errors."
integration: logfire
---
# OrcaRouter

See every model call your app makes through [OrcaRouter](https://www.orcarouter.ai): the full
conversation, each tool call, how many **tokens** (the units a model reads and bills by, a few
characters of text each) it used, how long it took, and any errors, as a **trace** (the full journey
of one request or agent run, made of nested **spans**, where each span is one unit of work with a
name, a start, and a duration) in Logfire.

OrcaRouter exposes an OpenAI-compatible API, so you use the standard OpenAI SDK with it and
[`logfire.instrument_openai()`][logfire.Logfire.instrument_openai] records every call. It also runs
gateway-level, zero-trust security for AI agents on the same endpoint, screening every prompt and
response and governing every tool call on a default-deny basis, with no application code changes.

## What you'll capture

- Each model call as a span, with its duration and any exceptions
- The full conversation, rendered so you can read it like a transcript
- Response details, including the number of tokens used
- Streaming responses and tool calls, shown as spans in the trace

!!! note "Prompts and responses are sent to Logfire"
    The full conversation (prompts, responses, and tool inputs) is recorded as span attributes and stored in Logfire, so it can include personal or proprietary data. Use [scrubbing](../../how-to-guides/scrubbing.md) to redact sensitive values before they leave your machine.

{{ before_you_start() }}

You'll also need an **OrcaRouter API key**, from your [OrcaRouter dashboard](https://www.orcarouter.ai). It starts with `sk-orca-`. The OpenAI SDK reads it from the `ORCAROUTER_API_KEY` environment variable.

## Installation

Install `logfire`:

{{ install_logfire() }}

This integration works with your existing `openai` package: nothing extra to install. If you don't
have it yet, `pip install openai`.

## Usage

Point an `openai.OpenAI` client at OrcaRouter with `base_url` and `api_key`, then add two lines to
your app: `logfire.configure()` to connect to your project, and
[`logfire.instrument_openai()`][logfire.Logfire.instrument_openai] to record every OrcaRouter call.

```python hl_lines="7-12" skip-run="true" skip-reason="external-connection"
import openai

import logfire

client = openai.OpenAI(
    base_url='https://api.orcarouter.ai/v1',
    api_key='sk-orca-...',  # your OrcaRouter API key, from the OrcaRouter dashboard
)

logfire.configure()
logfire.instrument_openai()  # instrument all OpenAI clients globally
# or logfire.instrument_openai(client) to instrument a specific client instance

response = client.chat.completions.create(
    model='orcarouter/auto',
    messages=[
        {'role': 'system', 'content': 'You are a helpful assistant.'},
        {'role': 'user', 'content': 'Please write me a limerick about Python logging.'},
    ],
)
print(response.choices[0].message.content)
```

With that you get:

- a span around the call to OrcaRouter which records duration and captures any exceptions that might occur
- human-readable display of the conversation with the model
- details of the response, including the number of tokens used

## Verify it worked

Run your program, then open your project in the
[Logfire web app](https://logfire.pydantic.dev/) and go to the **Live** view. Within a few seconds
you should see a span for the OrcaRouter call. Click it to read the conversation and see the token
count and duration.

## Troubleshooting

Not seeing your model calls in Logfire? Check these first:

- **`logfire.configure()` runs before `logfire.instrument_openai()`.** Configure the connection
  first, then instrument.
- **You instrument the client you actually call.** `instrument_openai()` with no argument covers all
  clients; if you pass a specific client, make sure it's the one making the request.
- **Your OrcaRouter client uses the right `base_url`.** Logfire instruments any OpenAI client, so the
  span appears as long as the client points at `https://api.orcarouter.ai/v1`.
- **Your Logfire write token is set.** In local development, run `logfire projects use <your-project>`;
  in production, set the `LOGFIRE_TOKEN` environment variable. See [Getting Started](../../index.md).
- **Your OrcaRouter call succeeded.** If the call itself fails (for example, a missing or invalid
  `ORCAROUTER_API_KEY`), check the span for the recorded exception.

## Advanced

### Methods covered

OrcaRouter follows the OpenAI API, so the same methods are covered as for
[OpenAI](openai.md#methods-covered):

- [`client.chat.completions.create`](https://platform.openai.com/docs/guides/text-generation/chat-completions-api): with and without `stream=True`
- [`client.completions.create`](https://platform.openai.com/docs/guides/text-generation/completions-api): with and without `stream=True`
- [`client.embeddings.create`](https://platform.openai.com/docs/guides/embeddings/how-to-get-embeddings)
- [`client.images.generate`](https://platform.openai.com/docs/guides/images/generations)

## Reference

- API reference: [`logfire.instrument_openai()`][logfire.Logfire.instrument_openai]
