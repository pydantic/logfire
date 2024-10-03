# Logfire Express Integration Example

This example demonstrates how to use OpenTelemetry to instrument an Express application and send traces and metrics to Logfire.

## Run the project

To run the example locally, you need a Logfire account and a project and a local installation of Node 20. If you don't have a Logfire account, create a free one [in Logfire](https://logfire.pydantic.dev/).

Clone the repository:

```bash
git clone https://github.com/pydantic/logfire.git
```

`cd` into the example directory and install:

```bash
cd examples/javascript/express
npm install
```

Then, add an .env file with your Logfire token and configuration:

```bash
# Used for reporting traces to Logfire
LOGFIRE_BASE_URL=https://logfire-api.pydantic.dev/
# The write token for your project
LOGFIRE_WRITE_TOKEN=your-write-token
EXPRESS_PORT=8080
```

Afterwards, you can start the example with `npm run start` and issue a network request to `http://localhost:8080/rolldice` using curl, for example:

```bash
curl http://localhost:8080/rolldice
```

If everything is set up correctly, you should see the response from the server and traces reported in Logfire.

## Customizing the example

The OpenTelemetry configuration is defined in the `instrumentation.ts` file, where `OTLPMetricExporter` and `OTLPTraceExporter` are created and used to send traces and metrics to Logfire. You can add more instrumentation to your application by following the [OpenTelemetry documentation](https://opentelemetry.io/docs/languages/js/).
