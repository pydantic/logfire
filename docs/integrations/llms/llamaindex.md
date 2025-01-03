---
integration: otel
---

The way we recommend instrumenting **LlamaIndex** is to use the OpenTelemetry specific instrumentation
provided by [OpenLLMetry]: [`opentelemetry-instrumentation-llamaindex`][opentelemetry-instrumentation-llamaindex].


## Installation

Install the [`opentelemetry-instrumentation-llamaindex`][opentelemetry-instrumentation-llamaindex] package:

```bash
pip install opentelemetry-instrumentation-llamaindex
```

## Usage

Let's use LlamaIndex with OpenAI as an example.

You only need to include the `LlamaIndexInstrumentor` and call its `instrument` method to enable the instrumentation.

```python hl_lines="5 8"
import logfire
from llama_index.core import VectorStoreIndex
from llama_index.llms.openai import OpenAI
from llama_index.readers.web import SimpleWebPageReader
from opentelemetry.instrumentation.llamaindex import LlamaIndexInstrumentor

logfire.configure()
LlamaIndexInstrumentor().instrument()

# URL for Pydantic's main concepts page
url = 'https://docs.pydantic.dev/latest/concepts/models/'

# Load the webpage
documents = SimpleWebPageReader(html_to_text=True).load_data([url])

# Create index from documents
index = VectorStoreIndex.from_documents(documents)

# Initialize the LLM
query_engine = index.as_query_engine(llm=OpenAI())

# Get response
response = query_engine.query('Can I use RootModels without subclassing them? Show me an example.')
print(str(response))
"""
Yes, you can use RootModels without subclassing them. Here is an example:

```python
from pydantic import RootModel

Pets = RootModel[list[str]]

my_pets = Pets.model_validate(['dog', 'cat'])

print(my_pets[0])
#> dog
print([pet for pet in my_pets])
#> ['dog', 'cat']
"""
```

## Instrument the underlying LLM

The `LlamaIndexInstrumentor` will specifically instrument the LlamaIndex library, not the LLM itself.
If you want to instrument the LLM, you'll need to instrument it separately:

- For **OpenAI**, you can use the OpenAI, you can check the [OpenAI documentation](llms/openai.md).
- For **Anthropic**, you can check the [Anthropic documentation](llms/anthropic.md).

If you are using a different LLM, and you can't find a way to instrument it, or you need any help,
feel free to [reach out to us](../../help.md)! :smile:

[OpenLLMetry]: https://www.traceloop.com/openllmetry
[opentelemetry-instrumentation-llamaindex]: https://github.com/traceloop/openllmetry/tree/main/packages/opentelemetry-instrumentation-llamaindex
