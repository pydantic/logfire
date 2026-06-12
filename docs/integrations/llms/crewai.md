---
title: "Pydantic Logfire Integrations: CrewAI"
description: "Instrument CrewAI multi-agent crews with Pydantic Logfire using OpenInference. Trace every agent, task, tool call, and LLM request."
integration: otel
---
# CrewAI

[CrewAI](https://docs.crewai.com/) orchestrates role-playing autonomous agents into collaborating "crews".
You can send full traces of every agent, task, tool call, and LLM request to **Logfire**.

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

```python skip-run="true" skip-reason="external-connection"
import os

from crewai import Agent, Crew, Process, Task
from openinference.instrumentation.crewai import CrewAIInstrumentor

import logfire

os.environ['OPENAI_API_KEY'] = 'your-openai-key'

logfire.configure()
CrewAIInstrumentor().instrument()

researcher = Agent(
    role='Researcher',
    goal='Explain a topic clearly and concisely',
    backstory='You are a knowledgeable analyst who values brevity.',
    llm='openai/gpt-4o-mini',
)

task = Task(
    description='Summarize what OpenTelemetry is in two sentences.',
    expected_output='A two-sentence summary.',
    agent=researcher,
)

crew = Crew(agents=[researcher], tasks=[task], process=Process.sequential)
print(crew.kickoff())
```

You'll see a nested trace in **Logfire** with the crew kickoff at the top, a span per task and agent, and the
underlying LLM and tool calls beneath them.

!!! tip
    CrewAI uses [LiteLLM](./litellm.md)-style model strings, so the provider-prefixed form
    `'openai/gpt-4o-mini'` is the safest way to specify a model.

!!! note
    If you also call [`logfire.instrument_openai()`][logfire.Logfire.instrument_openai] (or another LLM
    instrumentation), you may get duplicate LLM spans. Pass
    `CrewAIInstrumentor().instrument(create_llm_spans=False)` to let your dedicated LLM instrumentation own
    those spans instead.

## Managed prompts

You can keep your agents' prompts (roles, goals, backstories, and task descriptions) in
[Prompt Management](../../reference/advanced/prompt-management/index.md) and fetch them at runtime with the
Logfire SDK, so non-engineers can iterate on them without redeploying.

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
