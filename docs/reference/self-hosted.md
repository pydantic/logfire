# Self-Hosted Deployment with Helm

This reference provides an overview of the official [Logfire Helm chart](https://github.com/pydantic/logfire-helm-chart). Enabling easy deployment and management of Logfire on Kubernetes.

This chart is included in our [Enterprise plan](../enterprise.md), contact us at [sales@pydantic.dev](mailto:sales@pydantic.dev) for details.

### Key Benefits

* **Simplified Deployment:** Install and manage the entire application stack with a single command.
* **Flexible Configuration:** Easily adjust resource allocation, ingress settings, and authentication to your needs.
* **Production-Ready Defaults:** Built-in settings for high availability, resource limits, and health checks.
* **Repeatable & Versioned:** Manage your application deployment as code, ensuring consistency across environments.
* **Compliance Friendly:** Easily aligns with internal security standards and regulatory requirements by leveraging your organization's own infrastructure.

---

## Prerequisites

Before deploying, you will need the following:

* **Kubernetes Cluster:** A running Kuberentes cluster
* **External Resources:** A production-ready PostgreSQL database and object storage service (e.g., AWS S3, Google Cloud Storage, Azure Blob Storage).
* **Image Pull Secret:** Obtain credentials for accessing our private container images by contacting **sales@pydantic.dev**.

---

## Configuration Overview

Deploying Logfire successfully involves configuring essential parameters within your ```values.yaml``` file. Below is an overview of the topics you need to go over

### 1. Image Pull Secret

After receiving credentials from us, create a docker-registry secret in your Kubernetes cluster and reference its name in your ```values.yaml```.

### 2. Ingress & Hostname

Set ```ingress.hostname``` and ingress settings to expose Logfire at your desired URL.

### 3. Authentication (Dex)

The chart uses Dex as its identity service. You must configure at least one connector (like GitHub, OIDC, LDAP, etc.) so users can log in. You can find a full list of supported connectors in the [Dex documentation](https://dexidp.io/docs/connectors/).

### 4. External Services

Supply connection details for your PostgreSQL database and object storage.

For production environments, we recommend and can assist with configuring a robust, external PostgreSQL database tailored to your specific data volume requirements.

**Note**: The chart doesn't deploy production-grade databases or storage by default.

### Development-Only Options
For quick testing or development, the chart can deploy internal instances of Postgres and MinIO. These are enabled with the ```dev.deployPostgres``` and ```dev.deployMinio flags```.

:warning: **Warning:** These development services are not suitable for production use. They lack persistence, backup, and security configurations.

## Installation

For detailed, step-by-step instructions, default values, and configuration examples, please refer to the primary documentation in our GitHub repository [pydantic/logfire-helm-chart](https://github.com/pydantic/logfire-helm-chart)

The basic steps are the following:

### 1. Add the Helm Repository

```bash
# Add the repository
helm repo add Pydantic https://charts.pydantic.dev/

# Fetch the latest list of charts
helm repo update
```

### 2. Create your `custom-values.yaml`

Based on the configuration requirements outlined above, create a custom values file.

### 3. Install the chart

```bash
helm upgrade --install logfire pydantic/logfire -f custom-values.yaml
```

## Troubleshooting and support

Encountering issues? Open a detailed issue on [Github](https://github.com/pydantic/logfire-helm-chart/issues), including:

* Chart version
* Kubernetes version
* A sanitized copy of your ```values.yaml```
* Relevant logs or error messages

For commercial or enterprise support, contact [our sales team](mailto:sales@pydantic.dev).
