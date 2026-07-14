---
title: "Connect Genkit to the AI Gateway"
description: "Send Genkit model requests through the Logfire AI Gateway."
---

# Connect Genkit to the AI Gateway

Send requests from your Genkit application through Logfire to track model usage and apply gateway spending limits.

[Genkit](https://genkit.dev/) is Google's open-source framework for building AI applications. Both examples configure Genkit's OpenAI-compatible plugin with a gateway key and route.

## Before you start

- Complete the [AI Gateway prerequisites](index.md#before-you-start), including setting `LOGFIRE_GATEWAY_API_KEY` in your terminal.
- Use an existing Genkit project with the packages imported by your chosen example installed.

!!! note "Model data passes through Logfire"
    This configuration sends prompts, tool inputs, and model responses through the Logfire AI Gateway and the selected model provider. If gateway telemetry is enabled, Logfire stores the conversation content in your selected project. Calls to built-in providers count toward your gateway spend.

## TypeScript

Set `apiKey` to your gateway key and `baseURL` to the OpenAI-compatible gateway route. Copy the route and a supported model name from the Gateway **Connect** tab.

```typescript title="genkit-gateway.mts" hl_lines="15-16" skip-run="true" skip-reason="external-connection"
import { openAICompatible } from '@genkit-ai/compat-oai';
import { genkit } from 'genkit';
import { z } from 'zod';

const envSchema = z.object({
  LOGFIRE_GATEWAY_API_KEY: z.string(),
});

const env = envSchema.parse(process.env);

const ai = genkit({
  plugins: [
    openAICompatible({
      name: 'openai',
      apiKey: env.LOGFIRE_GATEWAY_API_KEY,
      baseURL: 'https://gateway-us.pydantic.dev/proxy/openai',
    }),
  ],
});

const { text } = await ai.generate({
  model: 'openai/gpt-5.4-mini',
  prompt: 'What is the weather in London?',
});

console.log(text);
```

## Go

Pass the same gateway key and route to Genkit's Go plugin.

```go title="genkit-gateway.go" hl_lines="25 27" skip-run="true" skip-reason="external-connection"
package main

import (
	"context"
	"log"
	"os"
	"time"

	"github.com/firebase/genkit/go/ai"
	"github.com/firebase/genkit/go/genkit"
	"github.com/firebase/genkit/go/plugins/compat_oai/openai"
	"github.com/openai/openai-go/option"
)

func main() {
	apiKey := os.Getenv("LOGFIRE_GATEWAY_API_KEY")
	if apiKey == "" {
		log.Fatal("LOGFIRE_GATEWAY_API_KEY is required")
	}

	ctx, cancel := context.WithTimeout(context.Background(), 60*time.Second)
	defer cancel()

	g := genkit.Init(ctx, genkit.WithPlugins(&openai.OpenAI{
		APIKey: apiKey,
		Opts: []option.RequestOption{
			option.WithBaseURL("https://gateway-us.pydantic.dev/proxy/openai"),
		},
	}))

	response, err := genkit.Generate(ctx, g,
		ai.WithPrompt("What is the weather in London?"),
		ai.WithModelName("openai/gpt-5.4-mini"),
	)
	if err != nil {
		log.Fatal(err)
	}

	log.Println(response.Text())
}
```

## Verify it worked

Run either example from your terminal. It prints the model response. That confirms the client reached the gateway. Organization admins can also open **AI Engineering** > **Gateway** > **Spending** to see usage for the key. If telemetry is enabled, open the selected project's **Live** view to inspect the request trace.

## Troubleshooting

- **The example reports that `LOGFIRE_GATEWAY_API_KEY` is missing:** set the environment variable in the same terminal where you run the example.
- **The request returns an authentication or model error:** copy the URL and model name again from the Gateway **Connect** tab, and confirm that the selected route supports the OpenAI request format.
