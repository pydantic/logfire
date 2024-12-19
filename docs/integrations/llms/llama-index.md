---
integration: logfire
---

**Logfire** supports instrumenting calls to different LLMs with one extra line of code.
Since LlamaIndex supports multiple LLMs, you can use **Logfire** to instrument calls to those LLMs.

## LlamaIndex with OpenAI

To use **Logfire** with LLamaIndex and OpenAI, you need to add the
[`logfire.instrument_openai()`][logfire.Logfire.instrument_openai] method to your code.

```python hl_lines="8"
from llama_index.core import VectorStoreIndex
from llama_index.llms.openai import OpenAI
from llama_index.readers.web import SimpleWebPageReader

import logfire

logfire.configure()
logfire.instrument_openai()

# URL for Pydantic's main concepts page
url = 'https://docs.pydantic.dev/latest/concepts/models/'

# Load the webpage
documents = SimpleWebPageReader(html_to_text=True).load_data([url])

# Create index from documents
index = VectorStoreIndex.from_documents(documents)

# Initialize the LLM
query_engine = index.as_query_engine(llm=OpenAI())

# Get response
response = query_engine.query('How can I use Pydantic models?')
print(str(response))
```

## LlamaIndex with Anthropic

To use **Logfire** with LLamaIndex and Anthropic, you need to add the
[`logfire.instrument_anthropic()`][logfire.Logfire.instrument_anthropic] method to your code.

```python hl_lines="8"
from llama_index.core import VectorStoreIndex
from llama_index.llms.anthropic import Anthropic
from llama_index.readers.web import SimpleWebPageReader

import logfire

logfire.configure()
logfire.instrument_anthropic()

# URL for Pydantic's main concepts page
url = 'https://docs.pydantic.dev/latest/concepts/models/'

# Load the webpage
documents = SimpleWebPageReader(html_to_text=True).load_data([url])

# Create index from documents
index = VectorStoreIndex.from_documents(documents)

# Initialize the LLM
query_engine = index.as_query_engine(llm=Anthropic())

# Get response
response = query_engine.query('How can I use Pydantic models?')
print(str(response))
```
