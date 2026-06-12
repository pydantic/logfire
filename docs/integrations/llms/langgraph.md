---
title: "Pydantic Logfire Integrations: LangGraph"
description: "Send LangGraph telemetry to Pydantic Logfire via the LangSmith OpenTelemetry bridge. Trace each node, tool call, and LLM request in your graph."
integration: otel
---
# LangGraph

[LangGraph](https://www.langchain.com/langgraph) builds stateful, multi-step agents as graphs. It emits
OpenTelemetry traces through the **LangSmith SDK** (bundled with `langchain`). When you call
[`logfire.configure()`][logfire.configure], **Logfire** installs the global OpenTelemetry tracer provider, and
the LangSmith tracer detects that provider and uses it — so your graph's spans flow straight into **Logfire**
with no exporter, endpoint, or API key configuration.

!!! note
    This is the same mechanism described on the [LangChain](./langchain.md) page. This page focuses on building
    a graph with `StateGraph`; the env vars and setup are identical.

## Installation

```bash
pip install logfire langchain langgraph langchain-openai
```

## Usage

Set the three `LANGSMITH_*` environment variables **before importing** `langchain`/`langgraph`, then call
[`logfire.configure()`][logfire.configure]:

```python skip-run="true" skip-reason="external-connection"
import os

# Must be set before importing langchain/langgraph
os.environ['LANGSMITH_OTEL_ENABLED'] = 'true'
os.environ['LANGSMITH_OTEL_ONLY'] = 'true'  # OTel only; no LangSmith backend, no API key needed
os.environ['LANGSMITH_TRACING'] = 'true'

from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph
from typing_extensions import TypedDict

import logfire

logfire.configure()  # sets the global OTel tracer provider that LangSmith detects


class State(TypedDict):
    topic: str
    joke: str


llm = ChatOpenAI(model='gpt-5-mini')


def tell_joke(state: State) -> dict:
    response = llm.invoke(f"Tell me a joke about {state['topic']}")
    return {'joke': response.content}


builder = StateGraph(State)
builder.add_node('tell_joke', tell_joke)
builder.add_edge(START, 'tell_joke')
builder.add_edge('tell_joke', END)
graph = builder.compile()

print(graph.invoke({'topic': 'otters'})['joke'])
```

You'll see a trace in **Logfire** with a span for the graph run, a span per node, and the underlying LLM and
tool calls nested beneath them.

!!! tip
    `LANGSMITH_OTEL_ONLY=true` stops LangSmith from also sending traces to its own backend, so you get
    **Logfire** only and don't need a `LANGSMITH_API_KEY`.

## Managed prompts

Keep your nodes' prompts in [Prompt Management](../../reference/advanced/prompt-management/index.md) and fetch
them at runtime:

```bash
pip install 'logfire[variables]'
```

```python skip="true"
from pydantic import BaseModel

import logfire

logfire.configure()


class JokeInputs(BaseModel):
    topic: str


prompt_var = logfire.template_var(
    name='prompt__joke',
    type=str,
    default='Tell me a joke about {{topic}}',
    inputs_type=JokeInputs,
)


def tell_joke(state):
    with prompt_var.get(JokeInputs(topic=state['topic']), label='production') as resolved:
        prompt = resolved.value
    response = llm.invoke(prompt)  # llm defined as in the example above
    return {'joke': response.content}
```

See [Use Prompts in Your Application](../../reference/advanced/prompt-management/application.md) for the full
workflow.
