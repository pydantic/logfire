# LLM Panels

Use **Logfire’s LLM panels** to inspect every round‑trip between your application and a large‑language model (LLM) in real time.
For each span Logfire captures:

* The ordered list of **system / user / assistant** messages
* Any **tool calls** (name, arguments, structured return value)
* **Files** referenced in the prompt (previewed inline or via link)
* **Model metadata** – latency, input / output tokens, and total cost

That context makes it easy to debug prompts, shrink token counts, and compare model performance side‑by‑side.

## Understand token & cost badges

Spans in the Live view may have a token usage badge on the right, indicated by a coin icon. If the badge contains a ∑ symbol, that means the badge is showing the sum of token usages across all descendants (children and nested children) of that span. If there's no ∑ symbol, then that specific span represents an LLM request and has recorded token usage on it directly.

![Expanded trace showing LLM spans](../../images/llm-panels/llm-trace-spans.png)

Hover over either to see:

- Model name
- Input tokens
- Output tokens
- Total cost (USD)

![Token‑usage pop‑over](../../images/llm-panels/connect-4-claude-usage-pop-over.png)

---

## Open the LLM details panel

Click an LLM span to open the details panel.

| Section        | What you’ll see                                             |
|----------------|-------------------------------------------------------------|
| **Messages**   | System, user, assistant, and tool messages in order.        |
| **Tool calls** | Name, arguments, and returned payload (objects or arrays).  |
| **Files**      | Links or inline previews of binary or blob uploads.         |
| **Metadata**   | Model name, token counts, and cost.                |

Logfire supports all major model hosts and many agent frameworks.

---

## Instrument your code

To get started the integration, please refer to [LLM integration guides](../../integrations/llms/pydanticai.md).

## Example LLM panel views

### Single‑prompt calls

```python
agent = Agent("google-gla:gemini-1.5-flash")
result = agent.run_sync("Which city is the capital of France?")
print(result.output)
```

![Basic LLM panel](../../images/llm-panels/basic-llm-panel.png)

Add a system prompt and Logfire captures it too:

```python
agent = Agent(
    "google-gla:gemini-1.5-flash",
    system_prompt="You are a helpful assistant."
)
result = agent.run_sync("Please write me a limerick about Python logging.")
```

![Panel with system prompt](../../images/llm-panels/basic-llm-panel-with-system-prompt.png)

---

### Agents and tool calls

Logfire displays every tool invocation and its structured response.

![Tool‑call example](../../images/llm-panels/llm-panel-with-tool.png)
![Weather‑tool example](../../images/llm-panels/llm-panel-with-tool-weather.png)
![Array‑response example](../../images/llm-panels/llm-panel-with-tool-array-response.png)

---

### File uploads

When a prompt includes a file, binary, blob, or URL, Logfire attaches a preview so you can verify exactly what the model received.

#### LLM panel with image url:
![File‑attachment with image url example](../../images/llm-panels/llm-panel-with-image-url.png)

#### LLM panel with PDF file:
![File‑attachment with binary image example](../../images/llm-panels/llm-panel-with-pdf-file.png)
