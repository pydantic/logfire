# Pydantic Logfire Enterprise

## Overview

In addition to the [Pro plan](https://pydantic.dev/pricing), Pydantic Logfire has two enterprise offerings:

- **Enterprise Cloud**: Fully managed, SLA-backed service
- **Enterprise Self-Hosted**: On-premises deployment via Kubernetes

## Enterprise Cloud

### Target Users

Organizations requiring:

- Service Level Agreements (SLAs)
- Custom Data Processing Agreements (DPAs)
- HIPAA Business Associate Agreements (BAAs)
- Invoice billing
- Custom retention
- Custom Single Sign-On (SSO)

### Features

| Feature                         | Description                                                        |
|---------------------------------|--------------------------------------------------------------------|
| **Full-Service Hosting**        | All operational complexity managed by our engineering team         |
| **Enhanced Support**            | Priority support with guaranteed SLAs, 24/7 dedicated assistance   |
| **Compliance & Custom Billing** | Tailored billing options and industry-specific compliance packages |
| **Custom Retention**            | Extended data retention beyond the standard 30-day SaaS offering   |
| **Custom SSO**                  | Login via custom identity providers (e.g. Okta, Azure AD, Auth0)   |


#### Single Sign-On (SSO) with Dex

- Logfire uses [Dex](https://github.com/dexidp/dex) under the hood, an open-source OIDC gateway, enabling quick
  integration with almost any identity provider.
- Works out-of-the-box with Okta, Azure AD, Auth0, Google Workspace, LDAP/AD, and any generic OIDC or SAML IdP.
- The same Dex config runs in both Enterprise Cloud and Self-Hosted, giving seamless SSO across deployments.


## Enterprise Self-Hosted

> **Note:** The Helm chart for Pydantic Logfire is now [open source](https://github.com/pydantic/logfire-helm-chart)

### Target Users

Organizations with:

- Highly sensitive data requirements
- Data sovereignty requirements
- Kubernetes expertise

### Features

| Feature | Description |
|---------|-------------|
| **Deployment** | Open-sourced Helm chart for quick deployment on any Kubernetes cluster |
| **Storage & Retention** | Parquet storage on any S3-compatible object storage with customizable retention policies |
| **Scalability** | Native Kubernetes scaling to match workload and cost requirements |

### Support Services

Enterprise Self-Hosted customers receive:

##### Installation & Configuration Guidance
- Production deployment best practices
- Environment-specific recommendations

##### Ongoing Troubleshooting
- Direct access to support engineers
- Assistance with operational and performance issues

##### Periodic Health Checks
- Optional system assessments
- Optimization and update recommendations

## Technical Architecture

### Core Technology Stack

Both deployment options use the same underlying technology:

- **Data Ingestion**: OpenTelemetry
- **Storage Format**: Parquet
- **Query Engine**: SQL-based queries via Apache DataFusion

### Key Technical Benefits

#### Open Standards Integration

- Built on established protocols and open formats
- Minimizes vendor lock-in risk
- Seamless integration with existing tooling
- Simplified migration path through OTel compatibility

#### AI Readiness

- SQL-based query layer provides familiar interface for AI tools
- Enables integration with LLM-powered workflows
- Supports automated analysis via agents
- Compatible with Logfire MCP server

#### Performance

- Powered by customized Apache DataFusion
- Recognized as the fastest single-node engine for Parquet queries
- Optimized for observability workloads

## Getting Started

For more information about Enterprise Cloud or Enterprise Self-Hosted solutions, [please contact](mailto:sales@pydantic.dev) our sales team.
