---
title: "Instrument DSPy: see every step of your DSPy program"
description: "Add a few lines to your DSPy code and see every module call, prompt, and model response in Logfire: the full conversation, token usage, duration, and any errors."
integration: logfire
---
# DSPy

See every step your [DSPy](https://dspy.ai/) program takes: each module call, the prompts it builds,
the model's responses, how many tokens it used, and any errors, as a **trace** (the full journey of
one request, made of nested **spans**, where each span is one unit of work with a name, a start, and a
duration) in Logfire. DSPy composes prompts and model calls into programs, and this integration shows
each nested step in one trace.

## What you'll capture

- Each DSPy module call as a span, with its duration and any exceptions
- The prompts DSPy builds and the model's responses
- Nested steps of your program, shown as child spans in the trace
- Response details, including the number of tokens used

!!! note "Prompts and responses are sent to Logfire"
    Your prompts, the model's responses, and any tool inputs are recorded as span attributes and
    stored in Logfire, so they can include personal or proprietary data. Use
    [scrubbing](../../how-to-guides/scrubbing.md) to redact sensitive values before they leave your
    machine.

{{ before_you_start() }}

You'll also need an API key for whichever model provider DSPy uses (for example, `OPENAI_API_KEY` for the `openai/...` model below). DSPy reads it from the provider's environment variable.

## Installation

Install `logfire` with the `dspy` extra and the DSPy package:

{{ install_logfire(extras=['dspy']) }}

```bash
pip install dspy
```

## Usage

Add two lines to your app: `logfire.configure()` to connect to your project, and
[`logfire.instrument_dspy()`][logfire.Logfire.instrument_dspy] to record every DSPy step.

```python hl_lines="5-6" skip-run="true" skip-reason="external-connection"
import dspy

import logfire

logfire.configure()
logfire.instrument_dspy()

lm = dspy.LM('openai/gpt-5-mini')
dspy.configure(lm=lm)


class ExtractInfo(dspy.Signature):
    """Extract structured information from text."""

    text: str = dspy.InputField()
    title: str = dspy.OutputField()
    headings: list[str] = dspy.OutputField()
    entities: list[dict[str, str]] = dspy.OutputField(desc='a list of entities and their metadata')


module = dspy.Predict(ExtractInfo)

text = (
    'Apple Inc. announced its latest iPhone 14 today. '
    'The CEO, Tim Cook, highlighted its new features in a press release.'
)
response = module(text=text)

print(response.title)
print(response.headings)
print(response.entities)
```

## Verify it worked

Run your program, then open your project in the
[Logfire web app](https://logfire.pydantic.dev/) and go to the **Live** view. Within a few seconds you
should see a trace for the DSPy run, with a span for each module call. Click into it to see the
prompts, responses, and token counts.

## Troubleshooting

Not seeing your DSPy steps in Logfire? Check these first:

- **`logfire.configure()` runs before `logfire.instrument_dspy()`.** Configure the connection first,
  then instrument.
- **You called `instrument_dspy()` exactly once.**
- **Your Logfire write token is set.** In local development, run `logfire projects use <your-project>`;
  in production, set the `LOGFIRE_TOKEN` environment variable. See [Getting Started](../../index.md).

## Reference

- API reference: [`logfire.instrument_dspy()`][logfire.Logfire.instrument_dspy]
- Underlying OpenTelemetry package:
  [`openinference-instrumentation-dspy`](https://pypi.org/project/openinference-instrumentation-dspy/)
