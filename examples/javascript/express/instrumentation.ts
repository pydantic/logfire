import { NodeSDK } from "@opentelemetry/sdk-node";
import { getNodeAutoInstrumentations } from "@opentelemetry/auto-instrumentations-node";
import { PeriodicExportingMetricReader } from "@opentelemetry/sdk-metrics";
import { OTLPTraceExporter } from "@opentelemetry/exporter-trace-otlp-proto";
import { OTLPMetricExporter } from "@opentelemetry/exporter-metrics-otlp-proto";
import { diag, DiagConsoleLogger, DiagLogLevel } from "@opentelemetry/api";
import { Resource } from "@opentelemetry/resources";
import {
  ATTR_SERVICE_NAME,
  ATTR_SERVICE_VERSION,
} from "@opentelemetry/semantic-conventions";
import { AsyncLocalStorageContextManager } from "@opentelemetry/context-async-hooks";
// For troubleshooting, set the log level to DiagLogLevel.DEBUG
diag.setLogger(new DiagConsoleLogger(), DiagLogLevel.INFO);

const BASE_LOGFIRE_URL =
  process.env.LOGFIRE_BASE_URL ?? "https://logfire-api.pydantic.dev/";

if (!process.env.LOGFIRE_WRITE_TOKEN) {
  throw new Error(
    "LOGFIRE_WRITE_TOKEN env variable is not set. Set it to the write token of your LogFire project",
  );
}

const traceExporter = new OTLPTraceExporter({
  url: `${BASE_LOGFIRE_URL}v1/traces`,
  headers: {
    Authorization: process.env.LOGFIRE_WRITE_TOKEN,
  },
});

const metricReader = new PeriodicExportingMetricReader({
  exporter: new OTLPMetricExporter({
    url: `${BASE_LOGFIRE_URL}v1/metrics`,
    headers: {
      Authorization: process.env.LOGFIRE_WRITE_TOKEN,
    },
  }),
  exportIntervalMillis: 1000,
});

const resource = new Resource({
  [ATTR_SERVICE_NAME]: "node-express",
  [ATTR_SERVICE_VERSION]: "1.0",
});

// use AsyncLocalStorageContextManager to manage parent <> child relationshps in async functions
const contextManager = new AsyncLocalStorageContextManager();

const sdk = new NodeSDK({
    contextManager,
    resource,
    traceExporter,
    metricReader,
    instrumentations: [
        getNodeAutoInstrumentations({
            // https://opentelemetry.io/docs/languages/js/libraries/#registration
            // This particular instrumentation creates a lot of noise on startup
            '@opentelemetry/instrumentation-fs': {
                enabled: false,
            },
        }),
    ],
});

sdk.start();
