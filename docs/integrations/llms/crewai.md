---
title: "Pydantic Logfire Integrations: CrewAI"
description: "Instrument CrewAI multi-agent crews with Pydantic Logfire using OpenInference. Trace every agent, task, tool call, and model request."
integration: otel
---
# CrewAI

[CrewAI](https://docs.crewai.com/) orchestrates role-playing autonomous agents into collaborating "crews".
You can send full traces of every agent, task, tool call, and large language model (LLM) request to **Logfire**.

CrewAI doesn't have a dedicated `logfire.instrument_crewai()` method, but it works out of the box with the
[OpenInference](https://github.com/Arize-ai/openinference) CrewAI instrumentor. This is possible because
[`logfire.configure()`][logfire.configure] sets up the global OpenTelemetry tracer provider, and the
OpenInference instrumentor exports its spans to that provider — so they end up in **Logfire** automatically.

## Installation

Install `logfire`, `crewai`, and the OpenInference CrewAI instrumentor:

```bash
pip install logfire crewai openinference-instrumentation-crewai
```

## Usage

Call [`logfire.configure()`][logfire.configure] and then `CrewAIInstrumentor().instrument()` **before** you
build and run your crew:

Set `OPENAI_API_KEY` in your terminal before starting the script:

```bash
export OPENAI_API_KEY='<your-openai-key>'
```

```python skip-run="true" skip-reason="external-connection"
from crewai import Agent, Crew, Process, Task
from crewai.tools import tool
from openinference.instrumentation.crewai import CrewAIInstrumentor

import logfire

logfire.configure()
CrewAIInstrumentor().instrument()


@tool('lookup_incident')
def lookup_incident(incident_id: str) -> str:
    """Look up the current status and owner of an incident by ID."""
    return f'{incident_id} is resolved; owner=platform-observability'


researcher = Agent(
    role='Researcher',
    goal='Resolve incident questions using the available operational tools',
    backstory='You are a reliability engineer who verifies facts with tools.',
    llm='openai/gpt-4o-mini',
    tools=[lookup_incident],
)

task = Task(
    description="Use lookup_incident for incident_id='incident-42', then report its status and owner.",
    expected_output='The status and owner returned by lookup_incident.',
    agent=researcher,
)

crew = Crew(agents=[researcher], tasks=[task], process=Process.sequential)
print(crew.kickoff())
```

You'll see a nested trace in **Live** and **Explore** with the crew kickoff at the top and a span per task and
agent beneath it. CrewAI agents also appear in the specialized **Agents** view — each run is detected and named
after the agent's role.

The CrewAI OpenInference instrumentation emits agent and chain spans, but not separate model-call spans, so the
**LLMs** view and the Agents view's token, model, and cost columns stay empty for CrewAI runs. The
[support matrix](../agent-frameworks/support-matrix.md) shows which columns each view populates.

!!! warning "Prompt and tool content"
    OpenInference can include task descriptions, outputs, tool arguments, and tool results in spans sent to
    Logfire. For sensitive workloads, pass
    `config=TraceConfig(hide_inputs=True, hide_outputs=True)` to `instrument()` after importing `TraceConfig`
    from `openinference.instrumentation`.

!!! tip
    CrewAI uses [LiteLLM](./litellm.md)-style model strings, so the provider-prefixed form
    `'openai/gpt-4o-mini'` is the safest way to specify a model.

!!! note
    If you also call [`logfire.instrument_openai()`][logfire.Logfire.instrument_openai] (or another LLM
    instrumentation), you may get duplicate LLM spans. Use the instrumentor's event-listener mode and pass
    `CrewAIInstrumentor().instrument(use_event_listener=True, create_llm_spans=False)` to let your dedicated
    LLM instrumentation own those spans instead. The `create_llm_spans` option has no effect in the default
    wrapper-based mode.

## Managed prompts

You can keep your agents' prompts (roles, goals, backstories, and task descriptions) in
[Prompt Management](../../reference/advanced/prompt-management/index.md) and fetch them at runtime with the
Logfire software development kit (SDK), so non-engineers can iterate on them without redeploying.

Install the variables extra:

```bash
pip install 'logfire[variables]'
```

Then fetch a versioned prompt and pass it into your agent:

```python skip="true"
from crewai import Agent
from pydantic import BaseModel

import logfire

logfire.configure()


class BackstoryInputs(BaseModel):
    domain: str


backstory_var = logfire.template_var(
    name='prompt__researcher_backstory',
    type=str,
    default='You are a knowledgeable analyst who values brevity.',
    inputs_type=BackstoryInputs,
)

with backstory_var.get(BackstoryInputs(domain='observability'), label='production') as resolved:
    backstory = resolved.value

researcher = Agent(
    role='Researcher',
    goal='Explain a topic clearly and concisely',
    backstory=backstory,
    llm='openai/gpt-4o-mini',
)
```

See [Use Prompts in Your Application](../../reference/advanced/prompt-management/application.md) for the full
workflow, including promoting versions and rollout targeting.
