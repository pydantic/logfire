---
title: "Instrument LlamaIndex: see every step of your query pipeline"
description: "Add a few lines to your LlamaIndex code and see every step in Logfire: the retrieval, model calls, token usage, duration, and any errors, as one trace."
integration: otel
---
# LlamaIndex

See every step your [LlamaIndex](https://www.llamaindex.ai/) query pipeline takes (loading and
indexing documents, retrieving context, and calling the model), how long each took, and any errors,
as a **trace** (the full journey of one request, made of nested **spans**, where each span is one unit
of work with a name, a start, and a duration) in Logfire.

We recommend instrumenting LlamaIndex with the OpenTelemetry instrumentation from
[OpenLLMetry]: [`opentelemetry-instrumentation-llamaindex`][opentelemetry-instrumentation-llamaindex].

## What you'll capture

- Each pipeline step as a span, with its duration and any exceptions
- Retrieval steps, showing which documents were pulled in as context
- Model calls, shown as child spans within the trace

## Before you start

You'll need a Logfire project and its **write token**, the credential your app uses to send data to
Logfire. Create a project and copy its token from **Project → Settings → Write tokens** in the
Logfire web app. New to Logfire? Start with [Getting Started](../../index.md), which walks through
creating a project and linking your machine.

## Installation

Install `logfire`, the LlamaIndex instrumentation package, and the LlamaIndex packages used in the
example below:

{{ install_logfire() }}

```bash
pip install opentelemetry-instrumentation-llamaindex \
    llama-index-core llama-index-llms-openai llama-index-readers-web html2text
```

## Usage

Call `logfire.configure()` to connect to your project, then
`LlamaIndexInstrumentor().instrument()` to record every LlamaIndex step. Here's a complete example
using LlamaIndex with OpenAI. Set your OpenAI API key in the `OPENAI_API_KEY` environment variable
before running it (get one from the [OpenAI dashboard](https://platform.openai.com/api-keys)):

```python title="main.py" hl_lines="8-9" skip-run="true" skip-reason="external-connection"
from llama_index.core import VectorStoreIndex
from llama_index.llms.openai import OpenAI
from llama_index.readers.web import SimpleWebPageReader
from opentelemetry.instrumentation.llamaindex import LlamaIndexInstrumentor

import logfire

logfire.configure()
LlamaIndexInstrumentor().instrument()

# URL for Pydantic's main concepts page
url = 'https://pydantic.dev/docs/validation/latest/concepts/models/'

# Load the webpage
documents = SimpleWebPageReader(html_to_text=True).load_data([url])

# Create index from documents
index = VectorStoreIndex.from_documents(documents)

# Initialize the LLM
query_engine = index.as_query_engine(llm=OpenAI())

# Get response
response = query_engine.query('Can I use RootModels without subclassing them? Show me an example.')
print(str(response))
```

This prints the model's answer to your query. Every LlamaIndex step in that run (indexing, retrieval, and the model call) is recorded in Logfire.

## Verify it worked

Run your program, then open your project in the
[Logfire web app](https://logfire.pydantic.dev/) and go to the **Live** view. Within a few seconds you
should see a trace for the query, with spans for the indexing, retrieval, and model call. Click into it
to see the duration of each step.

<!-- TODO(app-verify): confirm the Live-view span names for a LlamaIndex query and add a screenshot of the nested trace -->

## Troubleshooting

Not seeing your LlamaIndex steps in Logfire? Check these first:

- **`logfire.configure()` runs before `LlamaIndexInstrumentor().instrument()`.** Configure the
  connection first, then instrument.
- **You called `.instrument()` exactly once**, before running your query.
- **Your Logfire write token is set.** In local development, run `logfire projects use <your-project>`;
  in production, set the `LOGFIRE_TOKEN` environment variable. See [Getting Started](../../index.md).

## Advanced

### Instrument the underlying model

`LlamaIndexInstrumentor` instruments the LlamaIndex library itself, not the model behind it. To also
see the raw model calls (the full conversation and token usage), instrument the model separately:

- For **OpenAI**, see the [OpenAI documentation](./openai.md).
- For **Anthropic**, see the [Anthropic documentation](./anthropic.md).

Using a different model and can't find a way to instrument it, or need any help?
[Reach out to us](../../help.md).

## Reference

- Underlying OpenTelemetry package:
  [`opentelemetry-instrumentation-llamaindex`][opentelemetry-instrumentation-llamaindex]

[OpenLLMetry]: https://www.traceloop.com/openllmetry
[opentelemetry-instrumentation-llamaindex]: https://github.com/traceloop/openllmetry/tree/main/packages/opentelemetry-instrumentation-llamaindex
