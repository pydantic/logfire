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

For general information about setting up and configuring the OpenTelemetry Collector, see our [OpenTelemetry Collector guide](./otel-collector.md).

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
    endpoint: "https://logfire-us.pydantic.dev"
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

## 3. Collecting Metrics from Amazon Web Services (AWS)

The [AWS CloudWatch metrics receiver](https://github.com/open-telemetry/opentelemetry-collector-contrib/tree/main/receiver/awscloudwatchmetricsreceiver) allows you to collect metrics from Amazon CloudWatch and forward them to Logfire.

### 3.1 Prerequisites

1. An AWS account with CloudWatch metrics enabled
2. IAM credentials with appropriate permissions (see IAM Setup below)
3. OpenTelemetry Collector with the `awscloudwatchmetrics` receiver

### 3.2 IAM Setup

To collect metrics from AWS CloudWatch, you need to configure IAM credentials with the appropriate permissions:

#### 3.2.1 Required Permissions

The IAM role or user needs the following CloudWatch permissions:

- `cloudwatch:GetMetricData`: Retrieve metric data points
- `cloudwatch:GetMetricStatistics`: Get aggregated metric statistics
- `cloudwatch:ListMetrics`: List available metrics

For ECS-specific metrics, you may also need EC2 permissions:

- `ec2:DescribeTags`: Get resource tags
- `ec2:DescribeInstances`: Get instance information
- `ec2:DescribeRegions`: List available regions

### 3.3 Configuration

Create a collector configuration file with the AWS ECS container metrics receiver:

```yaml title="aws-metrics-collector.yaml"
receivers:
  # Collect ECS container metrics directly from the ECS task metadata endpoint
  awsecscontainermetrics:
    # Collection interval
    collection_interval: 60s

exporters:
  debug:
  otlphttp:
    # Configure the US / EU endpoint for Logfire.
    # - US: https://logfire-us.pydantic.dev
    # - EU: https://logfire-eu.pydantic.dev
    endpoint: "https://logfire-us.pydantic.dev"
    headers:
      Authorization: "Bearer ${env:LOGFIRE_TOKEN}"

extensions:
  health_check:
    endpoint: "0.0.0.0:13133"

service:
  pipelines:
    metrics:
      receivers: [awsecscontainermetrics]
      exporters: [otlphttp, debug]
  extensions: [health_check]
```

This configuration collects metrics directly from the ECS task metadata endpoint including:

- Container CPU utilization
- Container memory utilization
- Container network I/O metrics
- Container storage I/O metrics

**For CloudWatch Metrics**: If you need to collect metrics from other AWS services (RDS, ALB, etc.), use the [AWS Distro for OpenTelemetry (ADOT)](https://aws-otel.github.io/docs/introduction) collector image `public.ecr.aws/aws-observability/aws-otel-collector` which includes the `awscloudwatchmetrics` receiver.

### 3.4 Authentication

The AWS ECS container metrics receiver collects metrics directly from the ECS task metadata endpoint, so **no AWS credentials or IAM permissions are required** for the metrics collection itself.

However, you still need:

1. **ECS Task Execution Role permissions** for:
   - Pulling container images from ECR
   - Writing logs to CloudWatch Logs
   - Reading secrets from AWS Secrets Manager

2. **Logfire authentication** via a write token. Store the write token as a secret in AWS Secrets Manager and reference it as an environment variable.

### 3.5 Example deployment using Amazon ECS

This section shows how to deploy the OpenTelemetry Collector to Amazon ECS using an IAM role for tasks.

#### 3.5.1 Create ECS Task Role

Since the ECS container metrics receiver doesn't require AWS API access, we only need a basic ECS task execution role:

```bash
# Create the ECS task trust policy file
cat > ecs-task-trust-policy.json << 'EOF'
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "ecs-tasks.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
EOF

# Create the Secrets Manager policy for accessing the Logfire token
cat > secretsmanager-policy.json << 'EOF'
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "secretsmanager:GetSecretValue"
            ],
            "Resource": "arn:aws:secretsmanager:*:*:secret:logfire-token*"
        }
    ]
}
EOF

# Get your AWS account ID
export AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)

# Create the IAM role
aws iam create-role \
    --role-name LogfireMetricsCollectorRole \
    --assume-role-policy-document file://ecs-task-trust-policy.json \
    --description "ECS task role for Logfire metrics collector"

# Attach ECS task execution permissions
aws iam attach-role-policy \
    --role-name LogfireMetricsCollectorRole \
    --policy-arn arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy

# Grant access to read the Logfire token secret
aws iam put-role-policy \
    --role-name LogfireMetricsCollectorRole \
    --policy-name LogfireSecretsAccess \
    --policy-document file://secretsmanager-policy.json
```

#### 3.5.2 Store Logfire token in AWS Secrets Manager

Store your Logfire write token as an ECS secret using AWS Secrets Manager. This follows the [ECS best practices for specifying sensitive data](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/specifying-sensitive-data.html):

```bash
# Create the secret for Logfire token
aws secretsmanager create-secret \
    --name logfire-token \
    --description "Logfire write token for metrics collection" \
    --secret-string "your-logfire-write-token-here"
```

#### 3.5.3 Create a Dockerfile

Create a Dockerfile that uses the official OpenTelemetry Collector contrib image:

```dockerfile title="Dockerfile"
# Update the base image to the latest version as needed
FROM otel/opentelemetry-collector-contrib:0.128.0

# Copy the collector configuration to the default location
COPY aws-metrics-collector.yaml /etc/otelcol-contrib/config.yaml
```

#### 3.5.4 Create an ECS Task Definition

Create an ECS task definition that uses the IAM role. First, get your AWS account ID and create the task definition:

```bash
# Get your AWS account ID (reuse from earlier or get it again)
export AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
export AWS_REGION="us-east-1"  # Change to your preferred region

# Create the task definition using the account ID
cat > task-definition.json << EOF
{
  "family": "logfire-metrics-collector",
  "networkMode": "awsvpc",
  "requiresCompatibilities": ["FARGATE"],
  "cpu": "256",
  "memory": "512",
  "executionRoleArn": "arn:aws:iam::${AWS_ACCOUNT_ID}:role/LogfireMetricsCollectorRole",
  "taskRoleArn": "arn:aws:iam::${AWS_ACCOUNT_ID}:role/LogfireMetricsCollectorRole",
  "containerDefinitions": [
    {
      "name": "otel-collector",
      "image": "${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/logfire-metrics-collector:latest",
      "essential": true,
      "portMappings": [
        {
          "containerPort": 13133,
          "protocol": "tcp"
        }
      ],
      "environment": [
        {
          "name": "AWS_REGION",
          "value": "${AWS_REGION}"
        }
      ],
      "secrets": [
        {
          "name": "LOGFIRE_TOKEN",
          "valueFrom": "arn:aws:secretsmanager:${AWS_REGION}:${AWS_ACCOUNT_ID}:secret:logfire-token-XXXXXX"
        }
      ],
      "logConfiguration": {
        "logDriver": "awslogs",
        "options": {
          "awslogs-group": "/ecs/logfire-metrics-collector",
          "awslogs-region": "${AWS_REGION}",
          "awslogs-stream-prefix": "ecs"
        }
      }
    }
  ]
}
EOF
```

**Important**: Replace `XXXXXX` in the secret ARN with the actual suffix generated by AWS Secrets Manager. You can get the complete ARN by running:

```bash
aws secretsmanager describe-secret --secret-id logfire-token --query 'ARN' --output text
```

**Note**: This task definition uses a single IAM role (`LogfireMetricsCollectorRole`) for both execution and task permissions, which simplifies the setup while providing all necessary permissions:

- **ECS Task Execution**: Pull images from ECR, access secrets, write logs
- **CloudWatch Access**: Collect metrics from AWS CloudWatch APIs
- **Secrets Access**: Retrieve Logfire token from AWS Secrets Manager

The next step will show you how to create the ECR repository and build the image.

#### 3.5.5 Create ECR Repository and Build Container Image

Create an ECR repository and build your container image with the OpenTelemetry Collector configuration:

```bash
# Create an ECR repository
aws ecr create-repository \
    --repository-name logfire-metrics-collector \
    --region ${AWS_REGION}

# Get the ECR repository URI
export ECR_REPOSITORY_URI="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/logfire-metrics-collector"

# Create the project structure
mkdir -p logfire-otel-collector
cd logfire-otel-collector

# Create the OpenTelemetry Collector configuration (same as section 3.3)
cat > aws-metrics-collector.yaml << 'EOF'
receivers:
  awsecscontainermetrics:
    collection_interval: 60s

exporters:
  debug:
  otlphttp:
    endpoint: "https://logfire-us.pydantic.dev"
    headers:
      Authorization: "Bearer ${env:LOGFIRE_TOKEN}"

extensions:
  health_check:
    endpoint: "0.0.0.0:13133"

service:
  pipelines:
    metrics:
      receivers: [awsecscontainermetrics]
      exporters: [otlphttp, debug]
  extensions: [health_check]
EOF

# Create the Dockerfile
cat > Dockerfile << 'EOF'
FROM otel/opentelemetry-collector-contrib:0.128.0
COPY aws-metrics-collector.yaml /etc/otelcol-contrib/config.yaml
EOF

# Build and push the container image
aws ecr get-login-password --region ${AWS_REGION} | docker login --username AWS --password-stdin ${ECR_REPOSITORY_URI}
docker build --platform linux/amd64 -t logfire-metrics-collector .
docker tag logfire-metrics-collector:latest ${ECR_REPOSITORY_URI}:latest
docker push ${ECR_REPOSITORY_URI}:latest
```

#### 3.5.6 Deploy to ECS

**Prerequisites**: Before deploying, ensure you have the following AWS infrastructure:

- **ECS Cluster**: [Creating an Amazon ECS cluster](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/create-cluster.html)
- **VPC and Subnets**: Use existing VPC/subnets or [create new ones](https://docs.aws.amazon.com/vpc/latest/userguide/create-vpc.html)

For this example, we'll use the default VPC and public subnets for simplicity:

```bash
# Get your default VPC and subnets
export VPC_ID=$(aws ec2 describe-vpcs --filters "Name=is-default,Values=true" --query 'Vpcs[0].VpcId' --output text)
export SUBNET_IDS=$(aws ec2 describe-subnets --filters "Name=vpc-id,Values=$VPC_ID" --query 'Subnets[0:2].SubnetId' --output text | tr '\t' ',')

# Create ECS cluster
aws ecs create-cluster --cluster-name logfire-metrics-cluster

# Register the task definition
aws ecs register-task-definition --cli-input-json file://task-definition.json

# Create an ECS service
aws ecs create-service \
    --cluster logfire-metrics-cluster \
    --service-name logfire-metrics-collector \
    --task-definition logfire-metrics-collector:1 \
    --desired-count 1 \
    --launch-type FARGATE \
    --network-configuration "awsvpcConfiguration={subnets=[${SUBNET_IDS}],assignPublicIp=ENABLED}"
```

**Important Security Considerations:**

⚠️ **This example uses public subnets for simplicity**. For production deployments, you should:

- **Use private subnets** with NAT Gateway or VPC endpoints for outbound internet access
- **Disable public IP assignment** (`assignPublicIp=DISABLED`)
- **Create restrictive security groups** that only allow outbound HTTPS (port 443)
- **Use VPC endpoints** for AWS services (ECR, Secrets Manager, CloudWatch) to avoid internet routing

For production networking setup, see:

- [VPC and subnets](https://docs.aws.amazon.com/vpc/latest/userguide/create-vpc.html)
- [NAT Gateway](https://docs.aws.amazon.com/vpc/latest/userguide/vpc-nat-gateway.html)
- [VPC endpoints](https://docs.aws.amazon.com/vpc/latest/privatelink/vpc-endpoints.html)

Once the deployment is complete, you should be able to run the following query in Logfire to verify metrics are being received:

```sql
-- For ECS container metrics
SELECT metric_name, count(*) AS metric_count
FROM metrics
WHERE metric_name IN ('ecs.task.memory.utilized', 'ecs.task.cpu.utilized', 'ecs.task.network.rate.rx', 'ecs.task.network.rate.tx')
GROUP BY metric_name;
```

#### 3.5.7 Cost Considerations

**ECS Container Metrics**: The ECS container metrics receiver collects data directly from the ECS task metadata endpoint at **no additional cost**. This is much more cost-effective than using CloudWatch APIs.

**CloudWatch Metrics**: If you use the AWS Distro for OpenTelemetry (ADOT) to collect CloudWatch metrics, be aware that the `GetMetricData` API is **not included in the AWS free tier**. Monitor your CloudWatch API usage and costs, especially when collecting metrics at high frequencies or from many resources.
