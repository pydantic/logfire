---
title: "AI Gateway: OpenAI SDK"
description: "Route OpenAI SDK model calls through the Logfire AI Gateway."
---

# OpenAI SDK

The [OpenAI SDK](https://platform.openai.com/docs/libraries) is OpenAI's official client library for calling the OpenAI API. To route calls through the Logfire AI Gateway, point the client's base URL at the gateway and use a key from the Gateway **API Keys** tab in place of your OpenAI key.

## .NET {#dotnet}

```csharp title="openai-sdk-gateway.cs" skip-run="true" skip-reason="external-connection"
using OpenAI;
using OpenAI.Chat;

using var cts = new CancellationTokenSource(TimeSpan.FromSeconds(60));

var apiKey = Environment.GetEnvironmentVariable("LOGFIRE_GATEWAY_API_KEY");
if (string.IsNullOrWhiteSpace(apiKey))
{
    throw new InvalidOperationException("LOGFIRE_GATEWAY_API_KEY is required");
}

OpenAIClientOptions options = new()
{
    Endpoint = new Uri("https://gateway-us.pydantic.dev/proxy/openai")
};

ChatClient client = new(
    model: "gpt-5.4-mini",
    credential: new System.ClientModel.ApiKeyCredential(apiKey),
    options: options
);

ChatCompletion completion = await client.CompleteChatAsync(
    [new UserChatMessage("What is the weather in London?")],
    cancellationToken: cts.Token
);
Console.WriteLine(completion.Content[0].Text);
```

## Go

```go title="openai-sdk-gateway.go" skip-run="true" skip-reason="external-connection"
package main

import (
	"context"
	"fmt"
	"log"
	"os"
	"time"

	"github.com/openai/openai-go/v3"
	"github.com/openai/openai-go/v3/option"
	"github.com/openai/openai-go/v3/responses"
)

func main() {
	apiKey := os.Getenv("LOGFIRE_GATEWAY_API_KEY")
	if apiKey == "" {
		log.Fatal("LOGFIRE_GATEWAY_API_KEY is required")
	}

	client := openai.NewClient(
		option.WithAPIKey(apiKey),
		option.WithBaseURL("https://gateway-us.pydantic.dev/proxy/openai"),
	)

	ctx, cancel := context.WithTimeout(context.Background(), 60*time.Second)
	defer cancel()

	response, err := client.Responses.New(ctx, responses.ResponseNewParams{
		Model: "gpt-5.4-mini",
		Input: responses.ResponseNewParamsInputUnion{
			OfString: openai.String("What is the weather in London?"),
		},
	})
	if err != nil {
		log.Fatal(err)
	}

	fmt.Println(response.OutputText())
}
```

## TypeScript

```typescript title="openai-sdk-gateway.mts" skip-run="true" skip-reason="external-connection"
import OpenAI from 'openai';
import { z } from 'zod';

const envSchema = z.object({
  LOGFIRE_GATEWAY_API_KEY: z.string(),
});

const env = envSchema.parse(process.env);

const client = new OpenAI({
  apiKey: env.LOGFIRE_GATEWAY_API_KEY,
  baseURL: 'https://gateway-us.pydantic.dev/proxy/openai',
});

const response = await client.chat.completions.create({
  model: 'gpt-5.4-mini',
  messages: [{ role: 'user', content: 'What is the weather in London?' }],
});

console.log(response.choices[0]?.message.content);
```

## Python

```python title="openai-sdk-gateway.py" skip-run="true" skip-reason="external-connection"
import os

from openai import OpenAI

client = OpenAI(
    api_key=os.environ['LOGFIRE_GATEWAY_API_KEY'],
    base_url='https://gateway-us.pydantic.dev/proxy/openai',
)

response = client.chat.completions.create(
    model='gpt-5.4-mini',
    messages=[{'role': 'user', 'content': 'What is the weather in London?'}],
)

print(response.choices[0].message.content)
```
