---
integration: logfire
---
# Anthropic

**Logfire** supports instrumenting calls to [Anthropic](https://github.com/anthropics/anthropic-sdk-python) with the [`logfire.instrument_anthropic()`][logfire.Logfire.instrument_anthropic] method, for example:


```python hl_lines="7"
import anthropic
import logfire

client = anthropic.Anthropic()

logfire.configure()
logfire.instrument_anthropic()  # instrument all Anthropic clients globally
# or logfire.instrument_anthropic(client) to instrument a specific client instance

response = client.messages.create(
    max_tokens=1000,
    model='claude-3-haiku-20240307',
    system='You are a helpful assistant.',
    messages=[{'role': 'user', 'content': 'Please write me a limerick about Python logging.'}],
)
print(response.content[0].text)
```

With that you get:

* a span around the call to Anthropic which records duration and captures any exceptions that might occur
* Human-readable display of the conversation with the agent
* details of the response, including the number of tokens used

<figure markdown="span">
  ![Logfire Anthropic](../../images/logfire-screenshot-anthropic.png){ width="500" }
  <figcaption>Anthropic span and conversation</figcaption>
</figure>

<figure markdown="span">
  ![Logfire Anthropic Arguments](../../images/logfire-screenshot-anthropic-arguments.png){ width="500" }
  <figcaption>Span arguments including response details</figcaption>
</figure>

## Methods covered

The following Anthropic methods are covered:

- [`client.messages.create`](https://docs.anthropic.com/en/api/messages)
- [`client.messages.stream`](https://docs.anthropic.com/en/api/messages-streaming)
- [`client.beta.tools.messages.create`](https://docs.anthropic.com/en/docs/tool-use)

All methods are covered with both `anthropic.Anthropic` and `anthropic.AsyncAnthropic`.

## Streaming Responses

When instrumenting streaming responses, Logfire creates two spans — one around the initial request and one
around the streamed response.

Here we also use Rich's [`Live`][rich.live.Live] and [`Markdown`][rich.markdown.Markdown] types to render the response in the terminal in real-time. :dancer:

```python
import anthropic
import logfire
from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown

client = anthropic.AsyncAnthropic()
logfire.configure()
logfire.instrument_anthropic(client)


async def main():
    console = Console()
    with logfire.span('Asking Anthropic to write some code'):
        response = client.messages.stream(
            max_tokens=1000,
            model='claude-3-haiku-20240307',
            system='Reply in markdown one.',
            messages=[{'role': 'user', 'content': 'Write Python to show a tree of files 🤞.'}],
        )
        content = ''
        with Live('', refresh_per_second=15, console=console) as live:
            async with response as stream:
                async for chunk in stream:
                    if chunk.type == 'content_block_delta':
                        content += chunk.delta.text
                        live.update(Markdown(content))


if __name__ == '__main__':
    import asyncio

    asyncio.run(main())
```

Shows up like this in Logfire:

<figure markdown="span">
  ![Logfire Anthropic Streaming](../../images/logfire-screenshot-anthropic-stream.png){ width="500" }
  <figcaption>Anthropic streaming response</figcaption>
</figure>

## Amazon Bedrock

You can also log Anthropic LLM calls to Amazon Bedrock using the `AmazonBedrock` and `AsyncAmazonBedrock` clients.

```python
import anthropic
import logfire

client = anthropic.AnthropicBedrock(
    aws_region='us-east-1',
    aws_access_key='access-key',
    aws_secret_key='secret-key',
)

logfire.configure()
logfire.instrument_anthropic(client)
```
