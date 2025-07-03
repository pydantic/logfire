# Self-Hosted Deployment with Helm

This page provides a quick-start overview for deploying Logfire on Kubernetes using the official [Logfire Helm chart](https://github.com/pydantic/logfire-helm-chart).

This chart is included in our [Enterprise plan](../enterprise.md).
Contact us at [sales@pydantic.dev](mailto:sales@pydantic.dev) for details.

### Key Benefits

* **Simplified Deployment:** Install and manage the entire application stack with a single command.
* **Flexible Configuration:** Easily adjust resource allocation, ingress settings, and authentication to your needs.
* **Production-Ready Defaults:** Built-in settings for high availability, resource limits, and health checks.
* **Repeatable & Versioned:** Manage your application deployment as code, ensuring consistency across environments.
* **Compliance Friendly:** Leverage your own infrastructure to meet internal security standards.

---

## In-Depth Installation Guide

For a complete, step-by-step walkthrough including detailed configuration, prerequisites, and troubleshooting for common errors, please refer to our In-Depth [Self-Hosted Deployment Guide](../self-hosted/introduction.md).

The rest of this page serves as a high-level reference for experienced users.

---

## Quick Start

### Prerequisites

Before deploying, you will need the following:

* **Kubernetes Cluster:** A running Kuberentes cluster
* **External Resources:** A production-ready PostgreSQL database and object storage service (e.g., AWS S3, Google Cloud Storage, Azure Blob Storage).
* **Image Pull Secret:** Obtain credentials for accessing our private container images by contacting **sales@pydantic.dev**.

### Prepare your `values.yaml`

Create a custom `values.yaml` file to configure Logfire. This file will contain connection details for your database, object storage, identity provider, and ingress settings.

Our [full installation guide](../self-hosted/installation.md) provides a complete checklist and a detailed example `values.yaml` to get you started.

#### Development-Only Options
For quick testing or development, the chart can deploy internal instances of Postgres and MinIO. These are enabled with the ```dev.deployPostgres``` and ```dev.deployMinio flags```.

!!! warning
    These development services are not suitable for production use. They lack persistence, backup, and security configurations.

### Installation

Once your prerequisites are gathered and your custom `values.yaml` is prepared, you can deploy the chart.

#### Add the Helm Repository

```bash
# Add the repository
helm repo add Pydantic https://charts.pydantic.dev/

# Fetch the latest list of charts
helm repo update
```

#### Install the chart

```bash
helm upgrade --install logfire pydantic/logfire -f values.yaml
```

### Troubleshooting and support

If you encounter issues, we recommend first consulting the [Troubleshooting](../self-hosted/troubleshooting.md) section in our in-depth guide.

If your issue persists, please open a detailed issue on [Github](https://github.com/pydantic/logfire-helm-chart/issues), including:

* Chart version
* Kubernetes version
* A sanitized copy of your ```values.yaml```
* Relevant logs or error messages

For commercial or enterprise support, contact [our sales team](mailto:sales@pydantic.dev).
