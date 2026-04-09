---
title: AG2 (Multi-Agent Framework)
description: Instrument AG2 multi-agent conversations with Logfire spans for conversation flow, agent turns, and tool execution.
integration: logfire
---

[AG2](https://docs.ag2.ai) supports multi-agent orchestration patterns such as two-agent chat and group chat.
Use [`logfire.instrument_ag2()`][logfire.Logfire.instrument_ag2] to trace conversation lifecycle events, agent turns, and tool execution.

## What gets traced

`logfire.instrument_ag2()` creates spans for:

- **Conversation lifecycle** (`AG2 conversation`)
- **Group chat orchestration** (`AG2 group chat run`, `AG2 group chat round`)
- **Agent turns** (`AG2 agent turn`)
- **Tool execution** (`AG2 tool execution`)

LLM provider request spans are still produced by provider-specific integrations (for example [`instrument_openai()`][logfire.Logfire.instrument_openai]), so AG2 spans stay focused on orchestration.

## Install

```bash
pip install logfire "ag2[openai]>=0.11.4,<1.0"
```

## Basic usage

```python skip-run="true" skip-reason="external-connection"
import os

from autogen import AssistantAgent, GroupChat, GroupChatManager, LLMConfig, UserProxyAgent

import logfire


llm_config = LLMConfig(
    {
        'model': 'gpt-4o-mini',
        'api_key': os.getenv('OPENAI_API_KEY'),
        'api_type': 'openai',
    }
)


def is_termination(msg: dict[str, object]) -> bool:
    content = msg.get('content', '') or ''
    return isinstance(content, str) and 'TERMINATE' in content


proxy = UserProxyAgent(
    name='user_proxy',
    human_input_mode='NEVER',
    max_consecutive_auto_reply=10,
    code_execution_config=False,
    is_termination_msg=is_termination,
)
research = AssistantAgent(name='research_agent', system_message='Find relevant facts.', llm_config=llm_config)
analyst = AssistantAgent(
    name='analyst_agent',
    system_message='Summarize the findings and say TERMINATE when done.',
    llm_config=llm_config,
)


@proxy.register_for_execution()
@research.register_for_llm(description='Search for information')
def search_knowledge(query: str) -> str:
    return f'Results for {query}'


group_chat = GroupChat(agents=[proxy, research, analyst], messages=[], max_round=10)
manager = GroupChatManager(groupchat=group_chat, llm_config=llm_config, is_termination_msg=is_termination)

logfire.configure(send_to_logfire=False)
logfire.instrument_ag2(record_content=False)

# Optional: also instrument OpenAI request spans
logfire.instrument_openai()

proxy.run(manager, message='What is AG2?').process()
```

## Configuration

`logfire.instrument_ag2()` supports:

- `agent`: instrument a specific AG2 agent instance (or iterable of instances); if omitted, instrument globally.
- `record_content`: include message/tool payload content in span attributes. Defaults to `False`.
- `suppress_other_instrumentation`: suppress other OTEL instrumentation while AG2 conversation processing runs.

## Related docs

- [Logfire concepts](https://logfire.pydantic.dev/docs/concepts/)
- [AG2 documentation](https://docs.ag2.ai)
