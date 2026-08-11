---
title: "Audio Transcriptions"
description: "Transcribe audio through the Logfire AI Gateway with OpenAI-compatible audio/transcriptions requests."
---

# Audio Transcriptions

The AI Gateway proxies audio transcription requests the same way it proxies chat: point an OpenAI-compatible client at a gateway route and call its `/audio/transcriptions` endpoint. The request is the standard OpenAI `multipart/form-data` upload (the audio file rides along with the form fields), so `client.audio.transcriptions.create` works unchanged. Usage is recorded for every transcription call; estimated cost is tracked when pricing data is available for the model, and where the charge lands depends on the provider type: built-in provider usage draws from your prepaid gateway balance, while bring-your-own-key (BYOK) usage is billed directly by the upstream provider (see [Providers](index.md#providers)).

## Which providers can serve transcriptions

Transcriptions are available for provider types whose `/audio/transcriptions` endpoint the gateway proxies as an OpenAI-compatible request: **OpenAI**, **Azure Foundry**, **Ollama**, and **custom** OpenAI-compatible providers.

## Models and response formats

Two kinds of transcription models are metered differently:

- **Token-priced models** (`gpt-4o-transcribe`, `gpt-4o-mini-transcribe`, `gpt-transcribe`): the JSON response carries a usage object with audio and text token counts, and the gateway prices them from its model catalog. These work on both built-in and BYOK providers.
- **Duration-priced models** (`whisper-1`): the response reports the audio duration in seconds, which the gateway records as usage. These are BYOK-only for now.

On a **built-in** provider, use a token-priced model with the default `json` response format; other combinations are refused up front because their responses carry no usage the gateway can bill. On **BYOK** providers all response formats work (`json`, `verbose_json`, `text`, `srt`, `vtt`); if the provider has **Require cost data** enabled, formats that produce no usage (`text`/`srt`/`vtt`) are refused up front.

Streaming transcription and `audio/translations` are not supported through the gateway yet.

## Sending a transcription request

Address the request to `<gateway-base-url>/<route>/audio/transcriptions` as `multipart/form-data` with a `file` and a `model` field (plus the optional OpenAI fields: `language`, `prompt`, `temperature`, `response_format`). Uploads are capped at 25MB, matching OpenAI's limit.

The examples below use the `openai` route in the US region; see the [gateway base URLs](index.md#connect-an-sdk) for other regions.

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

Usage is recorded on every transcription request like any other gateway call (and estimated cost too, when pricing data is available for the model), so transcriptions show up in your **Spending** analytics and (when telemetry is enabled) as traces alongside the rest of your LLM traffic, with the transcript as the response text. The audio content itself never enters your telemetry: traces carry a summary of the form fields (model, filename, size), not the file bytes.

The `prompt` form field (context you give the model about the audio) goes through the gateway's input guardrails like any chat message; the audio content itself is not inspected.

## See also

- [AI Gateway](index.md): enabling the gateway, providers, routing, and connecting SDKs.
- [Embeddings](embeddings.md): the same pattern for embedding requests.
