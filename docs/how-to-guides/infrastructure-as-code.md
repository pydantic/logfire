---
title: "Manage Logfire with Infrastructure as Code"
description: "Manage Logfire resources as code."
---
Logfire supports Infrastructure as Code (IaC) via provider projects for different tools.

## Terraform and OpenTofu

- Terraform docs: [registry.terraform.io/providers/pydantic/logfire](https://registry.terraform.io/providers/pydantic/logfire/latest/docs)
- OpenTofu docs: [search.opentofu.org/provider/pydantic/logfire](https://search.opentofu.org/provider/pydantic/logfire/latest)
- Provider source: [github.com/pydantic/terraform-provider-logfire](https://github.com/pydantic/terraform-provider-logfire)

## Pulumi

- Published in the Pulumi Registry: [pulumi.com/registry/packages/logfire](https://www.pulumi.com/registry/packages/logfire/)
- Pulumi provider source: [github.com/pydantic/pulumi-logfire](https://github.com/pydantic/pulumi-logfire)

## What You Can Manage

Resources include:

- `logfire_project`
- `logfire_channel` (webhook and Opsgenie)
- `logfire_alert`
- `logfire_dashboard`
- `logfire_write_token`
- `logfire_read_token`
- `logfire_organization` (self-hosted only)

## Requirements

- Terraform CLI `1.8+` (per provider docs)
- A Logfire API key, passed as `api_key` or `LOGFIRE_API_KEY`
- A Logfire base URL, passed as `base_url` or `LOGFIRE_BASE_URL`, when the provider cannot infer the hosted region from the API key or when you use self-hosted Logfire

See [API keys](../reference/advanced/use-api-keys.md) for key creation and scopes.

## Quick Start

```hcl
terraform {
  required_providers {
    logfire = {
      source  = "pydantic/logfire"
    }
  }
}

provider "logfire" {
  # You can also set LOGFIRE_API_KEY. Hosted Logfire base URLs are inferred
  # from regional API keys; set base_url explicitly for self-hosted Logfire.
  api_key = var.logfire_api_key
}

resource "logfire_project" "production" {
  name        = "production"
  description = "Managed by IaC"
}
```

Apply with your tool of choice:

- Terraform: `terraform init && terraform apply`
- OpenTofu: `tofu init && tofu apply`

## Self-Hosted Note

Set `base_url` to your self-hosted Logfire endpoint when running outside Logfire Cloud.
The `logfire_organization` resource is self-hosted only and requires an API key with organization-level scope.
