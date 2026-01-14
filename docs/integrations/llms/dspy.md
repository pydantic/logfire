---
title: "Pydantic Logfire Integrations: DSPy"
description: "Instrument DSPy with Pydantic Logfire using OpenInference for end-to-end LLM workflow tracing."
integration: logfire
---
# DSPy

**Logfire** supports instrumenting [DSPy](https://dspy.ai/) with the
[`logfire.instrument_dspy()`][logfire.Logfire.instrument_dspy] method.

## Installation

Install `logfire` with the `dspy` extra and the DSPy package:

{{ install_logfire(extras=['dspy']) }}

```bash
pip install dspy-ai
```

## Usage

```python hl_lines="6"
import dspy

import logfire

logfire.configure()
logfire.instrument_dspy()

lm = dspy.LM("openai/gpt-5-mini")
dspy.configure(lm=lm)

class ExtractInfo(dspy.Signature):
    """Extract structured information from text."""

    text: str = dspy.InputField()
    title: str = dspy.OutputField()
    headings: list[str] = dspy.OutputField()
    entities: list[dict[str, str]] = dspy.OutputField(desc="a list of entities and their metadata")

module = dspy.Predict(ExtractInfo)

text = "Apple Inc. announced its latest iPhone 14 today." \
    "The CEO, Tim Cook, highlighted its new features in a press release."
response = module(text=text)

print(response.title)
print(response.headings)
print(response.entities)
```

[`logfire.instrument_dspy()`][logfire.Logfire.instrument_dspy] uses the `DSPyInstrumentor().instrument()` method of
the [`openinference-instrumentation-dspy`](https://pypi.org/project/openinference-instrumentation-dspy/) package.
