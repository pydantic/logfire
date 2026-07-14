---
title: "Connect the OpenAI SDK to the AI Gateway"
description: "Send OpenAI SDK model requests through the Logfire AI Gateway."
---

# Connect the OpenAI SDK to the AI Gateway

Send requests from an OpenAI SDK through Logfire to track model usage and apply gateway spending limits.

The [OpenAI SDK](https://platform.openai.com/docs/libraries) is available for several languages. In each client, replace the provider key with your gateway key and replace the default base URL with an OpenAI-compatible gateway route.

## Before you start

- Complete the [AI Gateway prerequisites](index.md#before-you-start), including setting `LOGFIRE_GATEWAY_API_KEY` in your terminal.
- Use an existing project with the OpenAI SDK for your chosen language installed.
- Copy an OpenAI-compatible route and supported model name from the Gateway **Connect** tab.

!!! note "Model data passes through Logfire"
    This configuration sends prompts and model responses through the Logfire AI Gateway and the selected model provider. If gateway telemetry is enabled, Logfire stores the conversation content in your selected project. Calls to built-in providers count toward your gateway spend.

## .NET {#dotnet}

Pass the gateway key and route to `ChatClient`.

```csharp title="openai-sdk-gateway.cs" hl_lines="6 14 19" skip-run="true" skip-reason="external-connection"
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

Pass the gateway key and route as client options.

```go title="openai-sdk-gateway.go" hl_lines="22-23" skip-run="true" skip-reason="external-connection"
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

Pass the gateway key and route to the `OpenAI` constructor.

```typescript title="openai-sdk-gateway.mts" hl_lines="11-12" skip-run="true" skip-reason="external-connection"
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

Set the equivalent `api_key` and `base_url` values on the Python client.

```python title="openai-sdk-gateway.py" hl_lines="6-7" skip-run="true" skip-reason="external-connection"
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

## Verify it worked

Run your chosen example from your terminal. It prints the model response. That confirms the client reached the gateway. Organization admins can also open **AI Engineering** > **Gateway** > **Spending** to see usage for the key. If telemetry is enabled, open the selected project's **Live** view to inspect the request trace.

## Troubleshooting

- **The example reports that `LOGFIRE_GATEWAY_API_KEY` is missing:** set the environment variable in the same terminal where you run the example.
- **The request returns an authentication or model error:** copy the URL and model name again from the Gateway **Connect** tab, and confirm that the selected route supports the OpenAI request format.
