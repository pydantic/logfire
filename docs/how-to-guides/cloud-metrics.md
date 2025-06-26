# Collecting Metrics from Cloud Providers

Cloud metrics provide valuable insights into the performance, health, and usage of your cloud infrastructure. By collecting metrics from your cloud provider and centralizing them in Logfire, you can create a single pane of glass for monitoring your entire infrastructure stack.

Key benefits of collecting cloud metrics include:

- **Single pane of glass visibility**: Correlate metrics across different cloud providers and services
- **Centralized alerting**: Set up consistent alerting rules across your entire infrastructure
- **Cost optimization**: Identify resource usage patterns and optimize spending
- **Performance monitoring**: Track application performance alongside infrastructure metrics

## 1. Why Use the OpenTelemetry Collector?

Rather than you giving us access to your cloud provider directly we recommend using the [OpenTelemetry Collector](https://opentelemetry.io/docs/collector/) to collect metrics from your cloud provider. The OpenTelemetry Collector is a vendor-agnostic service that can collect, process, and export telemetry data (metrics, logs, traces) from various sources.
The advantages of this approach include:

- **Security**: You maintain control over your cloud credentials and don't need to share them with external services
- **Data governance**: Filter sensitive or unnecessary metrics before they leave your environment
- **Cost control**: Reduce data transfer costs by filtering and sampling metrics locally
- **Flexibility**: Transform, enrich, or aggregate metrics before sending them to Logfire
- **Vendor lock in**: Send the same metrics to multiple monitoring systems if needed

For general information about setting up and configuring the OpenTelemetry Collector, see our [OpenTelemetry Collector guide](./otel-collector/otel-collector-overview.md).

One important consideration before you embark on this guide is what your overall data flow is going to be.
For example, you don't want to export your application metrics to Logfire and Google Cloud Monitoring and *also* export your Google Cloud Monitoring metrics to Logfire, you'll end up with duplicate metrics!

We recommend you export all application metrics to Logfire directly and then use the OpenTelemetry Collector to collect metrics from your cloud provider that are *not* already being exported to Logfire.

## 2. Collecting Metrics from Google Cloud Platform (GCP)

The [Google Cloud Monitoring receiver](https://github.com/open-telemetry/opentelemetry-collector-contrib/tree/main/receiver/googlecloudmonitoringreceiver) allows you to collect metrics from Google Cloud Monitoring (formerly Stackdriver) and forward them to Logfire.

### 2.1 Prerequisites

1. A GCP project with the Cloud Monitoring API enabled
2. Service account credentials with appropriate IAM permissions (see IAM Setup below)
3. OpenTelemetry Collector with the `googlecloudmonitoring` receiver

### 2.2 Enabling the Cloud Monitoring API

To enable the Cloud Monitoring API for your GCP project follow the steps listed in [the official documentation](https://cloud.google.com/monitoring/api/enable-api).

### 2.3 IAM Setup

To collect metrics from Google Cloud Monitoring, you need to create a service account with the appropriate permissions:

#### 2.3.1 Required Permissions

The service account needs the following specific roles:

- `roles/monitoring.viewer`: grants read-only access to Monitoring in the Google Cloud console and the Cloud Monitoring API.

See the [official documentation](https://cloud.google.com/monitoring/access-control) for a complete list of permissions required for the Monitoring API.

#### 2.3.2 Creating a Service Account

To create a service account you can use the Google Cloud CLI or the GCP Console. Here are the steps using the CLI:

```bash
gcloud iam service-accounts create logfire-metrics-collector \
    --display-name="Logfire Metrics Collector" \
    --description="Service account for collecting metrics to send to Logfire"
```

Grant the service account the necessary permissions:

```bash
export PROJECT_ID="your-gcp-project-id"
gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:logfire-metrics-collector@$PROJECT_ID.iam.gserviceaccount.com" \
    --role="roles/monitoring.viewer"
```

### 2.4 Configuration

Create a collector configuration file with the Google Cloud Monitoring receiver:

```yaml title="gcp-metrics-collector.yaml"
receivers:
  googlecloudmonitoring:
    # Your GCP project ID
    project_id: "${env:PROJECT_ID}"
    # Collection interval
    collection_interval: 60s
    # Example of metric names to collect
    # See https://github.com/open-telemetry/opentelemetry-collector-contrib/tree/main/receiver/googlecloudmonitoringreceiver#configuration
    metrics_list:
      - metric_name: "cloudsql.googleapis.com/database/cpu/utilization"
      - metric_name: "kubernetes.io/container/memory/limit_utilization"
      # This will collect the CPU usage for the container we are deploying the collector itself in!
      - metric_name: "run.googleapis.com/container/cpu/usage"

exporters:
  debug:
  otlphttp:
    # Configure the US / EU endpoint for Logfire.
    # - US: https://logfire-us.pydantic.dev
    # - EU: https://logfire-eu.pydantic.dev
    endpoint: "https://logfire-eu.pydantic.dev"
    headers:
      Authorization: "Bearer ${env:LOGFIRE_TOKEN}"

extensions:
  health_check:
    # The PORT env var is set by CloudRun
    endpoint: "0.0.0.0:${env:PORT:-13133}"

service:
  pipelines:
    metrics:
      receivers: [googlecloudmonitoring]
      exporters: [otlphttp, debug]
  extensions: [health_check]
```

### 2.5 Authentication

Authentication to Google Cloud via [Application Default Credentials (ADC)](https://cloud.google.com/docs/authentication/application-default-credentials).
If you are running on Kubernetes you will have to set up [Workload Identity](https://cloud.google.com/kubernetes-engine/docs/how-to/workload-identity) to allow the OpenTelemetry Collector to access Google Cloud resources.
If you are running on Cloud Run or other GCP services, the default service account will be used automatically.
You can either give the default service account the necessary permissions (in which case you can skip creating the service account above) or create a new service account and configure the workload running the OpenTelemetry Collector to use this service account.
The latter is advisable from a security perspective, as it allows you to limit the permissions of the service account to only what is necessary for the OpenTelemetry Collector.

Authentication to Logfire must happen via a write token.
It is recommended that you store the write token as a secret (e.g. in Kubernetes secrets) and reference it in the collector configuration file as an environment variable to avoid hardcoding sensitive information in the configuration file.

### 2.6 Example deployment using Cloud Run

This section shows how to deploy the OpenTelemetry Collector to Google Cloud Run using the service account created in section 2.3.

#### 2.6.1 Create a Dockerfile

First, create a Dockerfile that uses the official OpenTelemetry Collector contrib image and copies your configuration:

```dockerfile title="Dockerfile"
# Update the base image to the latest version as needed
# It's good practice to use a specific version tag for stability
FROM otel/opentelemetry-collector-contrib:0.128.0

# Copy the collector configuration created previously to the default location
COPY gcp-metrics-collector.yaml /etc/otelcol-contrib/config.yaml
```

#### 2.6.2 Create a secret with your Logfire token

To securely store your Logfire write token, create a secret in Google Secret Manager.

First [enable the Secrets Manager API](https://cloud.google.com/secret-manager/docs/configuring-secret-manager) for your project.
Using the Google Cloud CLI:

```bash
# Enable the Secret Manager API
gcloud services enable secretmanager.googleapis.com
```

Then, create a secret and grant the service account access to it:

```bash
# Set your project ID
export PROJECT_ID="your-gcp-project-id"
export LOGFIRE_TOKEN="your-logfire-write-token"
# Create the secret
echo -n "$LOGFIRE_TOKEN" | gcloud secrets create logfire-token --data-file=-
# Grant the service account access to the secret
gcloud secrets add-iam-policy-binding logfire-token \
  --member="serviceAccount:logfire-metrics-collector@$PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"
```

#### 2.6.2 Build and push the container image

Build and push your container image to Google Container Registry or Artifact Registry.

With the following project structure:

```text
.
├── Dockerfile
└── gcp-metrics-collector.yaml
```

You can run:

```bash
# Set your project ID
export PROJECT_ID="your-gcp-project-id"

# Set the port for health checks
# Set no CPU throttling so that the collector runs even though it is not receiving external HTTP requests
# Do not allow any external HTTP traffic to the service
# Set the service to use the service account created earlier
# Inject the project ID as an environment variable
# Set the minimum number of instances to 1 so that the collector is always running
# Inject the Logfire token secret as an environment variable

gcloud run deploy otel-collector-gcp-metrics \
--source . \
--project $PROJECT_ID \
--port 13133 \
--no-allow-unauthenticated \
--service-account logfire-metrics-collector@$PROJECT_ID.iam.gserviceaccount.com \
--set-env-vars PROJECT_ID=$PROJECT_ID \
--no-cpu-throttling \
--min-instances 1 \
--update-secrets=LOGFIRE_TOKEN=logfire-token:latest
```

Once the deployment is complete you should be able to run the following query in Logfire to verify metrics are being received:

```sql
SELECT metric_name, count(*) AS metric_count
FROM metrics
WHERE metric_name IN ('cloudsql.googleapis.com/database/cpu/utilization', 'kubernetes.io/container/memory/limit_utilization')
GROUP BY metric_name;
```

#### 2.6.4 Configuring scaling

Depending on the amount of metrics data points you are collecting you may need to do more advanced configuration of the OpenTelemetry Collector to handle the load.
For example, you may want to configure the `batch` processor to batch metrics before sending them to Logfire, or use the `memory_limiter` processor to limit memory usage.
You also may need to tweak the resources allocated to the Cloud Run service to ensure it can handle the load.
