# Logfire Cloudflare Worker Integration Example

This example is based on the scaffolding created from `npm create cloudflare@latest`, and uses the [otel-cf-workers package](https://github.com/evanderkoogh/otel-cf-workers) to instrument a Cloudflare Worker and send traces and metrics to Logfire.

## Run the project

To run the example locally, you need a Logfire account and a project and a local installation of Node 20. If you don't have a Logfire account, create a free one [in Logfire](https://logfire.pydantic.dev/).

Clone the repository:

```bash
git clone https://github.com/pydantic/logfire.git
```

`cd` into the example directory and install:

```bash
cd examples/javascript/cloudflare-worker
npm install
```

Edit the `wrangler.toml` file and add [your write token](https://logfire.pydantic.dev/docs/guides/advanced/creating-write-tokens/) and (optionally) the base URL of the Logfire API:

```toml
[vars]
LOGFIRE_WRITE_TOKEN="your-write-token"
LOGFIRE_BASE_URL="https://logfire-api.pydantic.dev/"
```

Then, run the worker locally:

```bash
npm run dev
```

If everything is set up correctly, when you visit `http://localhost:8787/` in your browser, you should see records reported in Logfire.
