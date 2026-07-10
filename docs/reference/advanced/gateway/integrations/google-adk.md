---
title: "AI Gateway: Google ADK"
description: "Route Google ADK model calls through the Logfire AI Gateway."
---

# Google ADK

[Google Agent Development Kit (ADK)](https://adk.dev/) is Google's framework for building multi-step, multi-agent AI systems. To route its model calls through the Logfire AI Gateway, set `LOGFIRE_GATEWAY_API_KEY` to a key from the Gateway **API Keys** tab. The Python example routes calls via LiteLLM (a library that translates between LLM provider APIs); the Go example connects directly to the gateway's Google Vertex proxy.

## Python

```python title="google-adk-gateway.py" skip-run="true" skip-reason="external-connection"
import asyncio
import os

from google.adk.agents import LlmAgent
from google.adk.models.lite_llm import LiteLlm
from google.adk.runners import InMemoryRunner
from google.genai import types

os.environ['OPENAI_API_KEY'] = os.environ['LOGFIRE_GATEWAY_API_KEY']
os.environ['OPENAI_BASE_URL'] = 'https://gateway-us.pydantic.dev/proxy/openai'

agent = LlmAgent(
    model=LiteLlm(model='openai/gpt-5.4-mini'),
    name='weather_agent',
    instruction='You are a concise weather assistant.',
)


async def main() -> None:
    runner = InMemoryRunner(agent=agent)
    session = await runner.session_service.create_session(
        app_name=runner.app_name,
        user_id='gateway-example-user',
    )
    content = types.Content(
        role='user',
        parts=[types.Part.from_text(text='What is the weather in London?')],
    )
    async for event in runner.run_async(
        user_id=session.user_id,
        session_id=session.id,
        new_message=content,
    ):
        if event.is_final_response() and event.content and event.content.parts:
            print(event.content.parts[0].text)


if __name__ == '__main__':
    asyncio.run(main())
```

## Go

The Go example routes Google Vertex model calls through `https://gateway-us.pydantic.dev/proxy/google-vertex`
and uses `gemini-2.5-flash`.

```go title="google-adk-gateway.go" skip-run="true" skip-reason="external-connection"
package main

import (
	"context"
	"fmt"
	"log"
	"net/http"
	"os"
	"time"

	adkmodel "google.golang.org/adk/v2/model"
	"google.golang.org/adk/v2/model/gemini"
	"google.golang.org/genai"
)

func main() {
	apiKey := os.Getenv("LOGFIRE_GATEWAY_API_KEY")
	if apiKey == "" {
		log.Fatal("LOGFIRE_GATEWAY_API_KEY is required")
	}

	ctx, cancel := context.WithTimeout(context.Background(), 60*time.Second)
	defer cancel()

	model, err := gemini.NewModel(ctx, "gemini-2.5-flash", &genai.ClientConfig{
		Backend: genai.BackendVertexAI,
		HTTPOptions: genai.HTTPOptions{
			BaseURL: "https://gateway-us.pydantic.dev/proxy/google-vertex",
			Headers: http.Header{
				"Authorization": []string{"Bearer " + apiKey},
			},
		},
	})
	if err != nil {
		panic(err)
	}

	request := &adkmodel.LLMRequest{
		Contents: []*genai.Content{
			genai.NewContentFromText("What is the weather in London?", genai.RoleUser),
		},
	}

	for response, err := range model.GenerateContent(ctx, request, false) {
		if err != nil {
			panic(err)
		}
		if response.Content == nil {
			continue
		}
		for _, part := range response.Content.Parts {
			if part.Text != "" {
				fmt.Println(part.Text)
			}
		}
	}
}
```
