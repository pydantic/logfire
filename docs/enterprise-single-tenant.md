---
title: Enterprise Dedicated Single Tenant
description: "Enterprise Dedicated is a fully managed, single-tenant deployment of Logfire running on isolated infrastructure provisioned and operated by Pydantic."
---

# Enterprise Dedicated: Single Tenant Deployment

## Overview

Enterprise Dedicated is a fully managed, single-tenant deployment of Logfire that runs on dedicated infrastructure provisioned and operated by Pydantic. Each tenant receives a fully isolated environment — their own virtual network, managed Kubernetes cluster, managed database, and object storage — ensuring complete data separation from other customers. The deployment region is fully configurable, allowing customers to choose the region that best meets their latency, data residency, or compliance requirements. Pydantic handles all provisioning, upgrades, and operational concerns; customers simply access their dedicated Logfire instance via a unique hostname.

> **Cloud support:** GCP is currently supported. Additional cloud providers are planned.

## Architecture

Each Logfire Dedicated environment provisions the following dedicated cloud resources for the tenant:

```
                                                          Pydantic
                                                       ┌─────────────────────┐
                                                       │  Monitoring &       │
                                                       │  Operations Cluster │
                                                       │                     │
                                                       │  ┌───────────────┐  │
                                                       │  │  Metrics,     │  │
                                                       │  │  Logs,        │  │
                                                       │  │  Alerts       │  │
                                                       │  └───────────────┘  │
                                                       └─────────▲───────────┘
                                                                 │
                                                        telemetry│(encrypted)
                                                                 │
┌──────────────────────────────────────────────────────────────────────────────────┐
│                  Tenant Isolated Environment (configurable region)               │
│                                                                                  │
│   ┌──────────────────────────────────────────────────────────────────────────┐   │
│   │                       Dedicated Virtual Network                          │   │
│   │                                                                          │   │
│   │   ┌──────────────────────────────────┐                                   │   │
│   │   │         Private Subnet           │                                   │   │
│   │   │                                  │                                   │   │
│   │   │   ┌────────────────────────┐     │    ┌──────────────────────────┐   │   │
│   │   │   │  Managed Kubernetes    │     │    │  Managed Database        │   │   │
│   │   │   │  Cluster               │     │    │  (PostgreSQL)            │   │   │
│   │   │   │                        │◀────┼───▶│  Private IP only        │   │   │
│   │   │   │  ┌──────────────────┐  │     │    └──────────────────────────┘   │   │
│   │   │   │  │  Logfire App     │  │     │                                   │   │
│   │   │   │  └────────┬─────────┘  │     │    ┌──────────────────────────┐   │   │
│   │   │   │           │            │     │    │  Object Storage          │   │   │
│   │   │   │    Workload Identity   │◀────┼───▶│  (Dedicated Bucket)     │   │   │
│   │   │   │    (short-lived creds) │     │    └──────────────────────────┘   │   │
│   │   │   └────────────────────────┘     │                                   │   │
│   │   └──────────────────────────────────┘                                   │   │
│   │               │                                                          │   │
│   │               ▼                                                          │   │
│   │        ┌─────────────┐                                                   │   │
│   │        │ NAT Gateway │──▶ Internet (egress only)                        │   │
│   │        └─────────────┘                                                   │   │
│   └──────────────────────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────────────────────┘
         ▲                             ▲
         │ encrypted tunnel            │ VPC peering (optional,
         │ (outbound-only,             │ same region & cloud provider)
         │  no public IPs)             ▼
         │                      ┌──────────────────────┐
  ┌──────────────┐              │ Customer's Own       │
  │ Cloudflare   │              │ Virtual Network      │
  │ Tunnel Proxy │              └──────────────────────┘
  │ (WAF + DDoS) │
  └──────────────┘
         ▲
         │ HTTPS
         │
   Customer Browser
```

### Components

| Component | Description |
|---|---|
| **Virtual Network** | A dedicated virtual private cloud with a private subnet, ensuring full network isolation from other tenants. |
| **Managed Kubernetes** | An autoscaling managed Kubernetes cluster running the Logfire application. The cloud provider handles node provisioning, OS patching, and resource optimization. |
| **Managed Database (PostgreSQL)** | A managed PostgreSQL instance accessible only via private IP within the tenant network. Stores all Logfire application data, authentication state, and configuration. |
| **Object Storage** | A dedicated storage bucket for application data, accessed via Workload Identity — no long-lived credentials are stored in the cluster. |
| **NAT Gateway** | Provides controlled outbound internet access for the cluster while keeping all resources on private IPs with no direct inbound exposure. |
| **Cloudflare Tunnel** | Secure ingress path from customers to the Logfire instance. Traffic is proxied through Cloudflare's network — the cluster has no public IP or open ingress ports. |
| **VPC Peering (optional)** | Customers can establish a VPC peering connection between the Logfire tenant network and their own virtual network, enabling private, low-latency connectivity for sending traces and telemetry directly to Logfire without traversing the public internet. Requires the same cloud provider and region. |
| **Monitoring & Operations** | Platform telemetry (metrics, logs, health signals) is streamed back to Pydantic's central operations cluster over an encrypted channel, enabling proactive monitoring, alerting, and incident response without requiring access to customer data. |

## Security

### Network Isolation

Every tenant environment is provisioned in a **dedicated virtual network** with its own private subnet. There is no network path between tenant environments. Key properties:

- **No public IPs on any compute or database resource.** The Kubernetes cluster and database instance communicate exclusively over private RFC 1918 addresses within the tenant network.
- **Private service peering** connects the managed database directly into the tenant network via the cloud provider's internal backbone — database traffic never traverses the public internet.
- **Firewall rules** restrict intra-network traffic to the tenant's own subnet CIDR. Only cloud provider health-check ranges are permitted for load balancer probes.
- **NAT gateway** mediates all outbound traffic, providing a controlled egress path without exposing any inbound surface.

### VPC Peering

For customers who want to send traces, logs, and telemetry to their Logfire instance over a private network path — without traversing the public internet — **VPC peering** is available. A peering connection can be established between the Logfire tenant network and the customer's own virtual network, provided both are on the **same cloud provider and in the same region**. This is why the deployment region is fully configurable: customers can choose the region where their workloads already run, then peer directly into the Logfire environment for low-latency, private connectivity.

### Secure Ingress (No Public Endpoints)

Tenant Logfire instances are exposed exclusively through **Cloudflare Tunnel**:

- An encrypted outbound-only tunnel connects the cluster to Cloudflare's edge — there are **no open inbound ports or public IPs** on the cluster.
- Traffic is proxied through Cloudflare, providing **DDoS protection and WAF** capabilities at the edge.
- Each tenant receives a unique hostname with HTTPS enforced end-to-end.

### Identity and Access

- **Workload Identity** binds cloud IAM service accounts to Kubernetes service accounts. The Logfire application accesses object storage and other cloud services using short-lived, automatically rotated credentials — no static keys are stored in the cluster.
- **Dedicated service accounts** are scoped per-tenant with least-privilege IAM roles (e.g., storage access only on the tenant's own bucket).

### Customer-Managed Encryption Keys (CMEK)

By default, all data is encrypted at rest using cloud provider-managed keys. For customers with additional compliance requirements, **CMEK support is available**:

- **Managed database** instances support CMEK, allowing customers to control the encryption key for their database.
- **Object storage** buckets support CMEK, giving customers control over storage encryption.
- **Kubernetes persistent volumes** support CMEK for any data written to cluster storage.

With CMEK enabled, revoking the key renders all tenant data unreadable, providing a cryptographic guarantee of data destruction.

### IP Allowlisting

Access to the Logfire instance can be restricted to specific IP addresses or CIDR ranges via **Cloudflare Access policies**. This allows customers to limit access to their corporate networks, VPN egress IPs, or other trusted sources — adding a network-level access control layer on top of application authentication.

### Operational Telemetry

Platform health telemetry (cluster metrics, resource utilization, availability signals) is collected from each tenant environment and streamed to Pydantic's central monitoring cluster over an encrypted channel. This enables:

- **Proactive alerting** on infrastructure health issues before they impact customers.
- **Capacity planning** and scaling decisions managed by Pydantic's operations team.
- **Incident response** with full visibility into infrastructure state.

Telemetry is limited to platform-level operational signals. **Customer application data is never included in the telemetry pipeline.**

### Summary of Security Properties

| Property | Implementation |
|---|---|
| Tenant isolation | Dedicated virtual network, subnet, and cloud resources per tenant |
| Data at rest encryption | Cloud provider-managed by default; CMEK available |
| Data in transit encryption | TLS end-to-end (Cloudflare edge to cluster) |
| No public endpoints | Cloudflare Tunnel (outbound-only); no public IPs |
| Credential management | Workload Identity; no static keys in cluster |
| Egress control | NAT gateway with logging |
| Access restriction | IP allowlisting via Cloudflare Access |
| Database access | Private IP only; private service peering |
| DDoS / WAF | Cloudflare proxy with built-in protection |
| Private connectivity | Optional VPC peering (same cloud provider & region) |
| Operational visibility | Encrypted telemetry to Pydantic monitoring (no customer data) |
