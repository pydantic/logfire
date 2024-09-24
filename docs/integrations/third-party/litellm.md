# LiteLLM

LiteLLM allows you to call over 100 Large Language Models (LLMs) using the same input/output format. It also supports Logfire for logging and monitoring.

To integrate Logfire with LiteLLM:
1. Set the `LOGFIRE_TOKEN` environment variable.
2. Add `logfire` to the callbacks of LiteLLM.

For more details, [check the official LiteLLM documentation.](https://docs.litellm.ai/docs/observability/logfire_integration)
