---
title: "AI Gateway: Genkit"
description: "Route Genkit model calls through the Logfire AI Gateway."
---

# Genkit

[Genkit](https://genkit.dev/) is Google's open-source framework for building AI-powered applications. To route its model calls through the Logfire AI Gateway, use Genkit's OpenAI-compatible plugin pointed at the gateway URL and set `LOGFIRE_GATEWAY_API_KEY` to a key from the Gateway **API Keys** tab.

## JavaScript

```typescript title="genkit-gateway.mts" skip-run="true" skip-reason="external-connection"
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

```go title="genkit-gateway.go" skip-run="true" skip-reason="external-connection"
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
