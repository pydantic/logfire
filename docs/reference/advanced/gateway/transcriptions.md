---
title: "Audio Transcriptions"
description: "Transcribe audio through the Logfire AI Gateway with OpenAI-compatible audio/transcriptions requests."
---

# Audio Transcriptions

The AI Gateway proxies audio transcription requests the same way it proxies chat: point an OpenAI-compatible client at a gateway route and call its `/audio/transcriptions` endpoint. The request is the standard OpenAI `multipart/form-data` upload (the audio file rides along with the form fields), so `client.audio.transcriptions.create` works unchanged. Usage is recorded for every transcription call, and estimated cost is tracked when pricing data is available for the model.

Transcriptions currently require a bring-your-own-key (BYOK) provider — the upstream provider bills your own credential directly, and requests routed to a Logfire built-in provider are refused for now (see [Providers](index.md#providers)).

## Which providers can serve transcriptions

Transcriptions are available for provider types whose `/audio/transcriptions` endpoint the gateway proxies as an OpenAI-compatible request: **OpenAI**, **Azure Foundry**, **Groq** (whisper models), **Mistral** (voxtral models), **Ollama**, and **custom** OpenAI-compatible providers.

## Models and response formats

Two kinds of transcription models are metered differently:

- **Token-priced models** (`gpt-4o-transcribe`, `gpt-4o-mini-transcribe`, `gpt-transcribe`): the JSON response carries a usage object with audio and text token counts, and the gateway prices them from its model catalog.
- **Duration-priced models** (`whisper-1`, Mistral's `voxtral-mini-latest`, Groq's `whisper-large-v3` and `whisper-large-v3-turbo`): the response reports the audio duration, which the gateway records as usage. Groq's responses carry no usage object at all, so request `response_format: verbose_json` there — the gateway meters the duration that format reports.

The `response_format` field passes through to the provider, so the model must support the format you request: `whisper-1` accepts all the OpenAI formats (`json`, `verbose_json`, `text`, `srt`, `vtt`), while the token-priced models above accept only `json` (`gpt-4o-transcribe-diarize` also documents `text`) — check your provider's own documentation for other models. If the provider has **Require cost data** enabled, formats that produce no usage (`text`/`srt`/`vtt`) are refused up front.

Streaming transcription and `audio/translations` are not supported through the gateway yet.

## Sending a transcription request

Address the request to `<gateway-base-url>/<route>/audio/transcriptions` as `multipart/form-data` with a `file` and a `model` field (plus the optional OpenAI fields: `language`, `prompt`, `temperature`, `response_format`). The gateway caps the request body at 30MB, slightly above the 25MB audio file limit OpenAI and Groq document, so a maximal upload plus its form fields still fits.

The examples below use an `openai` route in the US region pointing at your own OpenAI provider credential; see the [gateway base URLs](index.md#connect-an-sdk) for other regions.

=== "curl"

    ```bash
    curl https://gateway-us.pydantic.dev/proxy/openai/audio/transcriptions \
      -H "Authorization: Bearer <YOUR_GATEWAY_API_KEY>" \
      -F file=@recording.wav \
      -F model=gpt-4o-mini-transcribe
    ```

=== "Python (OpenAI SDK)"

    ```python skip-run="true" skip-reason="external-connection"
    from openai import OpenAI

    client = OpenAI(
        api_key='<YOUR_GATEWAY_API_KEY>',
        base_url='https://gateway-us.pydantic.dev/proxy/openai',
    )

    with open('recording.wav', 'rb') as audio_file:
        transcription = client.audio.transcriptions.create(
            file=audio_file,
            model='gpt-4o-mini-transcribe',
        )
    print(transcription.text)
    ```

=== "TypeScript (OpenAI SDK)"

    ```typescript
    import fs from 'node:fs'

    import OpenAI from 'openai'

    const client = new OpenAI({
      apiKey: '<YOUR_GATEWAY_API_KEY>',
      baseURL: 'https://gateway-us.pydantic.dev/proxy/openai',
    })

    const transcription = await client.audio.transcriptions.create({
      file: fs.createReadStream('recording.wav'),
      model: 'gpt-4o-mini-transcribe',
    })
    console.log(transcription.text)
    ```

Usage is recorded on every transcription request like any other gateway call (and estimated cost too, when pricing data is available for the model), so transcriptions show up in your **Spending** analytics and (when telemetry is enabled) as traces alongside the rest of your LLM traffic, with the transcript as the response text. The raw audio never enters your telemetry — traces carry a summary of the form fields (model, filename, size), not the file bytes — but the transcript text itself is recorded as the response message, just like a chat completion's output. Keep that in mind if your recordings contain sensitive content.

The `prompt` form field (context you give the model about the audio) goes through the gateway's input guardrails like any chat message; the audio content itself is not inspected.

## See also

- [AI Gateway](index.md): enabling the gateway, providers, routing, and connecting SDKs.
- [Embeddings](embeddings.md): the same pattern for embedding requests.
