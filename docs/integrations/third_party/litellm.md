# LiteLLM Proxy Server

Use [LiteLLM Proxy](https://docs.litellm.ai/docs/simple_proxy) to Log OpenAI, Azure, Vertex, Bedrock (100+ LLMs) to Logfire

Use LiteLLM Proxy for:
- Calling 100+ LLMs OpenAI, Azure, Vertex, Bedrock/etc. in the OpenAI ChatCompletions & Completions format
- Automatically Log all requests to Logfire (
For more details, [check the official LiteLLM documentation](https://docs.litellm.ai/docs/observability/logfire_integration)).


## Step 1. Create a Config for LiteLLM proxy

LiteLLM Requires a config with all your models defined - we can call this file `litellm_config.yaml`

[Detailed docs on how to setup litellm config - here](https://docs.litellm.ai/docs/proxy/configs)

```yaml
model_list:
  - model_name: gpt-4
    litellm_params:
      model: openai/fake
      api_key: fake-key
      api_base: https://exampleopenaiendpoint-production.up.railway.app/ # this is a working fake OpenAI endpoint setup by litellm. use this for testing only

litellm_settings:
  callbacks: ["logfire"] # 👈 Set logfire as a callback
```

Step 2. Start litellm proxy
Enter your `LOGFIRE_TOKEN` in the docker run command:

```shell
docker run \
    -v $(pwd)/litellm_config.yaml:/app/config.yaml \
    -p 4000:4000 \
    -e LOGFIRE_TOKEN=Kxxxxxx \
    ghcr.io/berriai/litellm:main-latest \
    --config /app/config.yaml --detailed_debug
```

Step 3. Test it - Make /chat/completions request to litellm proxy

```shell
curl -i http://localhost:4000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer sk-1234" \
  -d '{
    "model": "gpt-4",
    "messages": [
      {"role": "user", "content": "Hello, Claude gm!"}
    ]
}'
```

Expected output on Logfire below:
<img width="1302" alt="Xnapper-2024-07-24-08 43 16" src="https://github.com/user-attachments/assets/a1cc7841-dfc4-4f13-9d7b-9686668f2d34">





