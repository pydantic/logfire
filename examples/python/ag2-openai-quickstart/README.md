# AG2 + Logfire quickstart (real OpenAI calls)

This example runs a real AG2 multi-agent conversation and emits Logfire spans.

## Requirements

- Python environment with this repository installed
- `ag2[openai]` package
- `OPENAI_API_KEY`
- Optional: `LOGFIRE_TOKEN` (if you want to send traces to cloud)

## Run

```bash
python examples/python/ag2-openai-quickstart/main.py
```

Optional arguments:

```bash
python examples/python/ag2-openai-quickstart/main.py --model gpt-4o-mini --question "Plan a 2-day trip to Samarkand" --max-round 6
```

## Environment variables

```bash
export OPENAI_API_KEY="<your-openai-key>"
# Optional cloud export:
export LOGFIRE_TOKEN="<your-logfire-token>"
```

If `LOGFIRE_TOKEN` is not set, spans are still created locally with `send_to_logfire=False`.
