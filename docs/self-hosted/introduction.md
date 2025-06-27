# Self Hosted Introduction

Logfire can be deployed on-premises as an [enterprise](../enterprise.md) offering. This allows organizations the ability to fully manage their own data.

Self Hosting utilises helm charts to deploy Logfire into a Kubernetes cluster.

## Helm Chart

The [Helm Chart](https://helm.sh/) for Logfire is open source and hosted in github:

[https://github.com/pydantic/logfire-helm-chart](https://github.com/pydantic/logfire-helm-chart)

When you sign up for self-hosting, you will be provided with access to our private image repository for the associated **Logfire** containers.

## System Requirements

**Logfire** has been built from the ground up to be horizontally scalable. The self-hosted version shares the same code as the public deployment, and so is able to scale to high volumes of traffic.

With that in mind, here are some minimum requirements that you will need to deploy logfire self-hosted:

- A **Kubernetes** Cluster version `1.32` or greater
- A **PostgreSQL** Database version `16` or greater
- **Object Storage** such as Amazon S3, Azure Blob Storage or Google Cloud Storage
- At least `512GB` or more local SSD scratch disk for ingest, compaction and caching
- A **DNS/Hostname** to serve Logfire on. This does not need to be Internet accessible, but will need to be accessed over HTTP from any client.
- An **Identity Provider** for Authenticating Users such as Github, Google or Microsoft.  **Logfire** uses [Dex for authentication](https://dexidp.io/docs/connectors/)

Please view [installation](./installation.md) to find out how each of these are used.

## Client Configuration Instructions

To send data to a **Logfire** Self-hosted instance, the only change needed is to specify the base url in advanced options:

```python
import logfire

logfire.configure(
    ..., # other options
    advanced=logfire.AdvancedOptions(base_url="https://<your_logfire_hostname>")
)
```
