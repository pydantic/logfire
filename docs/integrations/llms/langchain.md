---
integration: built-in
---

# LangChain

Logfire provides instrumentation for [LangChain](https://www.langchain.com/) and [LangGraph](https://www.langchain.com/langgraph) via `logfire.instrument_langchain()`.

## Installation

Install Logfire with the `langchain` extra:

{{ install_logfire(extras=['langchain']) }}

## Usage

```python
import logfire

logfire.configure()
logfire.instrument_langchain()


def add(a: float, b: float) -> float:
    """Add two numbers."""
    return a + b


math_agent = create_agent('openai:gpt-4o', tools=[add], name='math_agent')
result = math_agent.invoke({'messages': [{'role': 'user', 'content': "what's 123 + 456?"}]})
print(result['messages'][-1].content)
```

The resulting trace looks like this in Logfire:

![Logfire LangChain Trace](../../images/logfire-screenshot-langchain.png)
