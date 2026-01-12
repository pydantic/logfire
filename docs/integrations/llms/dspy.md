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

lm = dspy.OpenAI(model='gpt-4o-mini')
dspy.settings.configure(lm=lm)


class BasicQA(dspy.Signature):
    question: str
    answer: str


predict = dspy.Predict(BasicQA)
result = predict(question='What is DSPy?')
print(result.answer)
```

[`logfire.instrument_dspy()`][logfire.Logfire.instrument_dspy] uses the `DSPyInstrumentor().instrument()` method of
the [`openinference-instrumentation-dspy`](https://pypi.org/project/openinference-instrumentation-dspy/) package.
