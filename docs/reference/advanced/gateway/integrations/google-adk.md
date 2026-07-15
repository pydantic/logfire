---
title: "Connect Google ADK to the AI Gateway"
description: "Send Google ADK model requests through the Logfire AI Gateway."
---

# Connect Google ADK to the AI Gateway

Send requests from your Google Agent Development Kit (ADK) agents through Logfire to track model usage and apply spending limits.

[Google ADK](https://adk.dev/) is Google's framework for building multi-step and multi-agent AI systems. The Python example uses LiteLLM, a library that translates between model-provider APIs. The Go example connects directly to the gateway's Google Vertex route.

## Before you start

- Complete the [AI Gateway prerequisites](index.md#before-you-start), including setting `LOGFIRE_GATEWAY_API_KEY` in your terminal.
- Use an existing Google ADK project with the packages imported by your chosen example installed.

!!! note "Model data passes through Logfire"
    This configuration sends prompts, tool inputs, and model responses through the Logfire AI Gateway and the selected model provider. If gateway telemetry is enabled, Logfire stores the conversation content in your selected project. Calls to built-in providers count toward your gateway spend.

## Python

The LiteLLM client uses the OpenAI-compatible gateway route. Copy the route and a supported model name from the Gateway **Connect** tab.

```python title="google-adk-gateway.py" hl_lines="9-10" skip-run="true" skip-reason="external-connection"
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

The Go client uses the provider-native Google Vertex route. Copy the Google Vertex URL and a supported Gemini model from the Gateway **Connect** tab.

```go title="google-adk-gateway.go" hl_lines="17 25 28 30" skip-run="true" skip-reason="external-connection"
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

## Verify it worked

Run either example from your terminal. It prints the model response. That confirms the client reached the gateway. Organization admins can also open **AI Engineering** > **Gateway** > **Spending** to see usage for the key. If telemetry is enabled, open the selected project's **Live** view to inspect the request trace.

## Troubleshooting

- **The example reports that `LOGFIRE_GATEWAY_API_KEY` is missing:** set the environment variable in the same terminal where you run the example.
- **The Python request fails:** copy an OpenAI-compatible URL and supported model from the Gateway **Connect** tab.
- **The Go request fails:** copy the Google Vertex URL and supported Gemini model from the **Connect** tab; an OpenAI-compatible route does not work with the provider-native Go client.
