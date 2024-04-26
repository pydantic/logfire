# OpenAI

## Introduction

Logfire supports instrumenting calls to OpenAI with one extra line of code.

```python hl_lines="6"
import openai
import logfire

client = openai.Client()

logfire.instrument_openai(client)  # (1)!

response = client.chat.completions.create(
    model='gpt-4',
    messages=[
        {'role': 'system', 'content': 'You are a helpful assistant.'},
        {'role': 'user', 'content': 'Please write me a limerick about Python logging.'},
    ],
)
print(response.choices[0].text)
```

1. In general, `logfire.instrument_openai()` should be all you need.

_For more information, see the [`instrument_openai()` API reference][logfire.Logfire.instrument_openai]._

With that you get:

* a span around the call to OpenAI which records duration and captures any exceptions that might occur
* Human-readable display of the conversation with the agent
* details of the response, including the number of tokens used

<figure markdown="span">
  ![Logfire OpenAI](../images/logfire-screenshot-openai.png){ width="500" }
  <figcaption>OpenAI span and conversation</figcaption>
</figure>

<figure markdown="span">
  ![Logfire OpenAI Arguments](../images/logfire-screenshot-openai-arguments.png){ width="500" }
  <figcaption>Span arguments including response details</figcaption>
</figure>

## Methods covered

The following OpenAI methods are covered:

- [`client.chat.completions.create`](https://platform.openai.com/docs/guides/text-generation/chat-completions-api) — with and without `stream=True`
- [`client.completions.create`](https://platform.openai.com/docs/guides/text-generation/completions-api) — with and without `stream=True`
- [`client.embeddings.create`](https://platform.openai.com/docs/guides/embeddings/how-to-get-embeddings)
- [`client.images.generate`](https://platform.openai.com/docs/guides/images/generations)

All methods are covered with both `openai.Client` and `openai.AsyncClient`.

For example, here's instrumentation of an image generation call:

```python
import openai
import logfire

async def main():
    client = openai.AsyncClient()
    logfire.instrument_openai(client)

    response = await client.images.generate(
        prompt='Image of R2D2 running through a desert in the style of cyberpunk.',
        model='dall-e-3',
    )
    url = response.data[0].url
    import webbrowser
    webbrowser.open(url)

if __name__ == '__main__':
    import asyncio
    asyncio.run(main())
```

Gives:

<figure markdown="span">
  ![Logfire OpenAI Image Generation](../images/logfire-screenshot-openai-image-gen.png){ width="500" }
  <figcaption>OpenAI image generation span</figcaption>
</figure>

## Streaming Responses

When instrumenting streaming responses, Logfire creates two spans — one around the initial request and one
around the streamed response.

Here we also use Rich's [`Live`][rich.live.Live] and [`Markdown`][rich.markdown.Markdown] types to render the response in the terminal in real-time. :dancer:

```python
import openai
import logfire
from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown

client = openai.AsyncClient()
logfire.instrument_openai(client)

async def main():
    console = Console()
    with logfire.span('Asking OpenAI to write some code'):
        response = await client.chat.completions.create(
            model='gpt-4',
            messages=[
                {'role': 'system', 'content': 'Reply in markdown one.'},
                {'role': 'user', 'content': 'Write Python to show a tree of files 🤞.'},
            ],
            stream=True
        )
        content = ''
        with Live('', refresh_per_second=15, console=console) as live:
            async for chunk in response:
                if chunk.choices[0].delta.content is not None:
                    content += chunk.choices[0].delta.content
                    live.update(Markdown(content))

if __name__ == '__main__':
    import asyncio
    asyncio.run(main())
```

Shows up like this in Logfire:

<figure markdown="span">
  ![Logfire OpenAI Streaming](../images/logfire-screenshot-openai-stream.png){ width="500" }
  <figcaption>OpenAI streaming response</figcaption>
</figure>
