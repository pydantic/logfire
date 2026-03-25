# OTel GenAI Spans Reference

Source: https://opentelemetry.io/docs/specs/semconv/gen-ai/gen-ai-spans/

## Span Naming

| Operation | Format | Example |
|-----------|--------|---------|
| Inference | `{gen_ai.operation.name} {gen_ai.request.model}` | `chat gpt-4` |
| Tool execution | `execute_tool {gen_ai.tool.name}` | `execute_tool get_weather` |

## Operation Names

`chat`, `text_completion`, `generate_content`, `embeddings`, `retrieval`, `create_agent`, `invoke_agent`, `execute_tool`

## Inference Span Attributes

**Required:**
- `gen_ai.operation.name` — e.g. `chat`
- `gen_ai.provider.name` — e.g. `anthropic`

**Conditionally Required:**
- `gen_ai.request.model` — exact vendor model name
- `error.type` — if operation failed

**Recommended:**
- `gen_ai.response.model` — actual model that generated response
- `gen_ai.response.id` — unique completion identifier
- `gen_ai.response.finish_reasons` — string[] reasons model stopped
- `gen_ai.usage.input_tokens` — total input tokens (includes cached)
- `gen_ai.usage.output_tokens` — total output tokens
- `gen_ai.usage.cache_creation.input_tokens` — tokens written to cache
- `gen_ai.usage.cache_read.input_tokens` — tokens served from cache
- `gen_ai.request.temperature`, `gen_ai.request.top_p`, `gen_ai.request.top_k`
- `gen_ai.request.max_tokens`, `gen_ai.request.stop_sequences`, `gen_ai.request.seed`
- `gen_ai.request.frequency_penalty`, `gen_ai.request.presence_penalty`
- `server.address`, `server.port`

**Opt-In (sensitive):**
- `gen_ai.input.messages` — chat history (structured JSON)
- `gen_ai.output.messages` — model responses (structured JSON)
- `gen_ai.system_instructions` — system prompts (structured JSON)
- `gen_ai.tool.definitions` — available tool definitions

**Span Kind:** CLIENT (or INTERNAL for same-process models)

**Set at span creation (for sampling):** `gen_ai.operation.name`, `gen_ai.provider.name`, `gen_ai.request.model`, `server.address`, `server.port`

## Tool Execution Span Attributes

**Required:**
- `gen_ai.operation.name` = `execute_tool`

**Recommended:**
- `gen_ai.tool.name` — tool name
- `gen_ai.tool.type` — `function`, `extension`, `datastore`
- `gen_ai.tool.call.id` — tool call identifier
- `gen_ai.tool.description` — tool description

**Opt-In (sensitive):**
- `gen_ai.tool.call.arguments` — parameters passed
- `gen_ai.tool.call.result` — tool execution result

**Span Kind:** INTERNAL

## Message Structure

Messages use a `role` + `parts` structure:

```json
[
  {
    "role": "user",
    "parts": [{"type": "text", "content": "Weather in Paris?"}]
  },
  {
    "role": "assistant",
    "parts": [{"type": "tool_call", "id": "call_xyz", "name": "get_weather", "arguments": {"location": "Paris"}}]
  },
  {
    "role": "tool",
    "parts": [{"type": "tool_call_response", "id": "call_xyz", "result": "rainy, 57F"}]
  }
]
```

Output messages add `finish_reason`. System instructions are a list of parts (no role wrapper).

## Key Implementation Notes

- `gen_ai.usage.input_tokens` SHOULD include all token types including cached tokens
- Don't record instructions/inputs/outputs by default — provide opt-in mechanism
- Use exact vendor-supplied model names
- `gen_ai.provider.name` acts as discriminator for telemetry flavor
