---
title: "Manage Logfire with Infrastructure as Code"
description: "Manage Logfire resources with Terraform, OpenTofu, or Pulumi."
---
Manage your Logfire projects, dashboards, alerts, and credentials with configuration files.
Infrastructure as Code (IaC) lets you review and apply these changes with your application configuration.

## Terraform and OpenTofu

Use the [Logfire provider](https://registry.terraform.io/providers/pydantic/logfire/latest/docs)
with Terraform or [OpenTofu](https://search.opentofu.org/provider/pydantic/logfire/latest).
The examples and resource list below come from the latest stable Terraform provider release, {{ terraform_release }}.

### What you can manage

{{ terraform_resources }}

## Quick start

Create a [Logfire API key](../reference/advanced/use-api-keys.md) with the
[scopes required by your resources](https://registry.terraform.io/providers/pydantic/logfire/latest/docs#required-scopes).
Set `LOGFIRE_API_KEY` to that key in your environment.

Save this configuration as `main.tf`:

{{ terraform_quick_start }}

Apply the configuration:

=== "Terraform"
    ```bash
    terraform init
    terraform apply
    ```

=== "OpenTofu"
    ```bash
    tofu init
    tofu apply
    ```

Review the plan before you approve it. Applying this configuration creates a project in your API key's organization.
You should see the project in Logfire after the command completes.

{{ terraform_configuration }}

## Self-hosted deployments

Set `base_url` to your self-hosted Logfire endpoint.
Check the provider's [self-hosted compatibility and credential requirements](https://registry.terraform.io/providers/pydantic/logfire/latest/docs#self-hosted-compatibility)
before you apply the configuration.

## Pulumi

Use the [Pulumi Logfire package](https://www.pulumi.com/registry/packages/logfire/)
for configuration in your programming language.
Its releases come from the Terraform provider, but can follow a different release schedule.
See the [Pulumi provider repository](https://github.com/pydantic/pulumi-logfire) for its source.

## Troubleshooting

For permission errors or an unavailable self-hosted API, follow the provider's
[credential troubleshooting guide](https://registry.terraform.io/providers/pydantic/logfire/latest/docs#troubleshooting-credentials).
