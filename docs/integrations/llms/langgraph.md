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

from langchain_core.messages import HumanMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

import logfire

logfire.configure()  # sets the global OTel tracer provider that LangSmith detects


tool_calls: list[str] = []


@tool
def lookup_incident(incident_id: str) -> str:
    """Look up the current status and owner of an incident by ID."""
    tool_calls.append(incident_id)
    return f'{incident_id} is resolved; owner=platform-observability'


llm = ChatOpenAI(model='gpt-5-mini', temperature=0).bind_tools([lookup_incident])


def call_model(state: MessagesState) -> dict:
    return {'messages': [llm.invoke(state['messages'])]}


builder = StateGraph(MessagesState)
builder.add_node('agent', call_model)
builder.add_node('tools', ToolNode([lookup_incident]))
builder.add_edge(START, 'agent')
builder.add_conditional_edges('agent', tools_condition, {'tools': 'tools', END: END})
builder.add_edge('tools', 'agent')
graph = builder.compile()

result = graph.invoke(
    {
        'messages': [
            HumanMessage(
                content="Use lookup_incident with incident_id='incident-42', then report the status and owner."
            )
        ]
    }
)
if tool_calls != ['incident-42']:
    raise RuntimeError(f'expected one tool call for incident-42, received {tool_calls}')
print(result['messages'][-1].content)
```

The example fails unless the graph executes its native `ToolNode`. You'll see a trace in **Logfire** with a span
for the graph run, a span per node, and the underlying LLM and `lookup_incident` tool calls nested beneath them.

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
