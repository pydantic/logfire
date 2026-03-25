# OTel GenAI Agent Spans Reference

Source: https://opentelemetry.io/docs/specs/semconv/gen-ai/gen-ai-agent-spans/

## Span Naming

| Operation | Format | Example |
|-----------|--------|---------|
| Invoke agent | `invoke_agent {gen_ai.agent.name}` | `invoke_agent MathTutor` |
| Create agent | `create_agent {gen_ai.agent.name}` | `create_agent MathTutor` |

## Span Hierarchy

```
[CLIENT] invoke_agent "invoke_agent MathTutor"
  ├─ gen_ai.operation.name: "invoke_agent"
  ├─ gen_ai.agent.name: "MathTutor"
  ├─ gen_ai.provider.name: "openai"
  │
  ├─ [INTERNAL] chat "chat gpt-4"
  │    ├─ gen_ai.operation.name: "chat"
  │    └─ gen_ai.input.messages: [...]
  │
  └─ [INTERNAL] execute_tool "execute_tool calculator"
       ├─ gen_ai.operation.name: "execute_tool"
       └─ gen_ai.tool.name: "calculator"
```

- **invoke_agent** contains zero or more **chat** spans and **execute_tool** spans
- **create_agent** is separate, not nested under invoke_agent
- Span kind: CLIENT (remote agent) or INTERNAL (in-process agent)

## Invoke Agent Attributes

**Required:**
- `gen_ai.operation.name` = `invoke_agent`
- `gen_ai.provider.name` — e.g. `anthropic`

**Conditionally Required (if available):**
- `gen_ai.agent.name` — human-readable name
- `gen_ai.agent.id` — unique system identifier
- `gen_ai.agent.description` — free-form description
- `gen_ai.agent.version` — version string
- `gen_ai.conversation.id` — session/thread ID
- `gen_ai.request.model` — model name
- `gen_ai.output.type` — `text`, `json`, `image`, `speech`
- `error.type` — if operation failed
- `server.port` — if `server.address` is set

**Recommended:**
- `gen_ai.response.model` — actual model that generated response
- `gen_ai.response.id` — completion identifier
- `gen_ai.response.finish_reasons` — string[]
- `gen_ai.usage.input_tokens` — total input tokens
- `gen_ai.usage.output_tokens` — total output tokens
- `gen_ai.usage.cache_creation.input_tokens`
- `gen_ai.usage.cache_read.input_tokens`
- `gen_ai.request.temperature`, `gen_ai.request.top_p`
- `gen_ai.request.max_tokens`, `gen_ai.request.stop_sequences`
- `gen_ai.request.frequency_penalty`, `gen_ai.request.presence_penalty`
- `server.address`

**Opt-In (sensitive):**
- `gen_ai.input.messages` — chat history
- `gen_ai.output.messages` — model responses
- `gen_ai.system_instructions` — system prompts
- `gen_ai.tool.definitions` — available tool definitions

**Set at span creation (for sampling):** `gen_ai.operation.name`, `gen_ai.provider.name`, `gen_ai.request.model`, `server.address`, `server.port`

## Agent Identification Attributes

- `gen_ai.agent.id` — unique system identifier (e.g. `asst_5j66UpCpwteGg4YSxUnt7lPY`)
- `gen_ai.agent.name` — human-readable name (e.g. `Math Tutor`)
- `gen_ai.agent.description` — free-form description
- `gen_ai.agent.version` — version string

## Conversation Context

- `gen_ai.conversation.id` — correlates messages across invocations (thread/session ID)
