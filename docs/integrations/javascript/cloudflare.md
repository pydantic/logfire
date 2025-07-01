---
integration: logfire
---

# Cloudflare

To instrument your Cloudflare Workers and send spans to Logfire, install the `@pydantic/logfire-cf-workers` and `@pydantic/logfire-api` NPM packages:

```sh
npm install @pydantic/logfire-cf-workers @pydantic/logfire-api
```

Next, add the Node.js compatibility flag to your Wrangler configuration:
- For `wrangler.toml`: `compatibility_flags = [ "nodejs_compat" ]`
- For `wrangler.jsonc`: `"compatibility_flags": ["nodejs_compat"]`

Add your [Logfire write token](https://logfire.pydantic.dev/docs/how-to-guides/create-write-tokens/) to your `.dev.vars` file:

```sh
LOGFIRE_TOKEN=your-write-token
LOGFIRE_ENVIRONMENT=development
```

The `LOGFIRE_ENVIRONMENT` variable is optional and specifies the environment name for your service.

For production deployment, refer to the [Cloudflare documentation on managing and deploying secrets](https://developers.cloudflare.com/workers/configuration/secrets/). You can set secrets using the Wrangler CLI:

```sh
npx wrangler secret put LOGFIRE_TOKEN
```

Finally, wrap your handler with the instrumentation. The `instrument` function will automatically configure Logfire using your environment variables:

```ts
import * as logfire from "@pydantic/logfire-api";
import { instrument } from "@pydantic/logfire-cf-workers";

const handler = {
  async fetch(): Promise<Response> {
    logfire.info("info span from inside the worker body");
    return new Response("hello world!");
  },
} satisfies ExportedHandler;

export default instrument(handler, {
	service: {
		name: 'my-cloudflare-worker',
		namespace: '',
		version: '1.0.0',
	},
});
```

A complete working example is available in the [examples/cf-worker](https://github.com/pydantic/logfire-js/tree/main/examples/cf-worker) directory.

!!! info
    If you're testing your Worker with Vitest, add the following configuration to your `vitest.config.mts` to ensure proper module loading:

    ```ts
    export default defineWorkersConfig({
      test: {
        deps: {
          optimizer: {
            ssr: {
              enabled: true,
              include: ['@pydantic/logfire-cf-workers'],
            },
          },
        },
        poolOptions: {
          workers: {
            // ...
          },
        },
      },
    });
    ```
