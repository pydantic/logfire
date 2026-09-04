---
title: "Provision Group Access with SCIM"
description: "Configure Logfire Enterprise SCIM endpoints so your identity provider can discover existing users and synchronize membership for mapped groups."
---

# Provision group access with SCIM

Keep Logfire access aligned with identity-provider groups without managing each member by hand. Logfire Enterprise provides a focused System for Cross-domain Identity Management (SCIM) 2.0 interface that lets your identity provider discover existing Logfire users and synchronize their membership in mapped groups. A group mapping assigns an identity-provider group to an organization role and, optionally, project-specific roles.

Logfire implements a focused SCIM subset:

- **User discovery** finds an existing Logfire account by email address. It does not create, update, deactivate, or delete accounts.
- **Group provisioning** adds or removes existing users from configured group mappings. It applies the organization and project roles assigned to each mapping.

This is not a complete user and group lifecycle API. If your identity provider requires resource discovery, user or group creation, updates, deactivation, or deletion, contact [Logfire support](mailto:support@pydantic.dev) before configuring it.

!!! note "Enterprise feature"
    SCIM provisioning is an Enterprise feature. This page documents the Enterprise Cloud and Enterprise Self-Hosted endpoints. For an Enterprise Dedicated deployment, contact [Logfire support](mailto:support@pydantic.dev) for its base URL and configuration.

## Prerequisites

Before configuring your identity provider:

1. [Configure single sign-on](how-to-guides/sso-setup.md) and its group mappings.
2. In Logfire, go to **Organization settings → API keys**, create an organization API key, and grant it only the **SCIM provisioning** (`organization:scim`) scope. See [Using API Keys to Access Public APIs](reference/advanced/use-api-keys.md).
3. Copy the API key when Logfire displays it. You cannot view it again.

For managed deployments, go to **Organization settings → Single sign-on** to find the provider name and manage its group mappings. The identity provider must already exist before its SCIM endpoint is available. The group identifier must exactly match the group name or ID sent by your identity provider.

For a self-hosted deployment, configure group-to-role mappings in the deployment before enabling SCIM. Contact [Logfire support](mailto:support@pydantic.dev) if you need help with the deployment configuration.

## Choose the base URL

Use the base URL for your deployment:

| Deployment | SCIM base URL |
| --- | --- |
| Enterprise Cloud, US region | `https://api-us.pydantic.dev/api/scim/{provider_name}` |
| Enterprise Cloud, EU region | `https://api-eu.pydantic.dev/api/scim/{provider_name}` |
| Enterprise Self-Hosted | `{api_origin}/api/scim` |

For managed deployments, replace `{provider_name}` with the exact provider name shown under **Organization settings → Single sign-on**. The provider must belong to the same organization as the API key. For self-hosted deployments, replace `{api_origin}` with the API origin for that deployment.

Send the organization API key as a bearer token with every request:

```http
Authorization: Bearer YOUR_SCIM_API_KEY
```

## Supported operations

| Method and path | Behavior |
| --- | --- |
| `GET /Users?filter=userName eq "email"` | Finds an existing user by email. Managed deployments return only users who already belong to the API key's organization. |
| `GET /Users/{user_email}` | Gets an existing user by email. |
| `GET /Groups?filter=displayName eq "group"` | Finds a configured group mapping by its exact group name or ID. |
| `GET /Groups/{group_id}` | Gets a configured group mapping. |
| `PATCH /Groups/{group_id}` | Applies `Add` or `Remove` operations to the mapping's members and returns `204 No Content`. |

The collection endpoints support only the filters shown in the table, including the exact attribute name, spacing, and double quotes. Compound filters are not supported. They return at most one resource. Group responses describe the mapped group but do not list its current members.

The API does not support `POST`, `PUT`, or `DELETE` operations for users or groups. It also does not expose `/ServiceProviderConfig`, `/ResourceTypes`, or `/Schemas`. Groups and users must already exist, so do not enable identity-provider actions that create or manage their lifecycle.

## Choose a compatible identity-provider setup

The current interface is designed for existing-user discovery and group-membership changes, not a provider's default end-to-end SCIM lifecycle flow.

- **Microsoft Entra ID:** The documented `PATCH /Groups/{group_id}` format matches [Entra's group-member add and remove requests](https://learn.microsoft.com/en-us/entra/identity/app-provisioning/use-scim-to-provision-users-and-groups#update-group-add-members). Configure provisioning to use only existing Logfire users and existing group mappings. User and group creation, updates, and deactivation are not supported.
- **Okta:** [Okta Group Push](https://developer.okta.com/docs/api/openapi/okta-scim/guides/scim-20/#update-specific-group-membership) is not currently compatible with this endpoint. Okta sends lowercase operation names and filtered member-removal paths, while Logfire currently accepts only the exact operations documented below. Custom Okta app integrations can also replace group membership with `PUT`, which Logfire does not support. Use [SSO group mappings](how-to-guides/sso-setup.md) to apply access when users sign in, or contact [Logfire support](mailto:support@pydantic.dev).

For another identity provider, compare its group-membership request format with [Supported operations](#supported-operations) before enabling provisioning. A provider can report success for an operation that the current Logfire endpoint does not apply, so verify the resulting roles in Logfire during setup.

## Test user discovery

Set the base URL and API key for your deployment, then query an existing user's Logfire email address:

```bash
export SCIM_BASE_URL='https://api-us.pydantic.dev/api/scim/your-provider-name'
export LOGFIRE_SCIM_TOKEN='YOUR_SCIM_API_KEY'

curl --get "$SCIM_BASE_URL/Users" \
  --header "Authorization: Bearer $LOGFIRE_SCIM_TOKEN" \
  --data-urlencode 'filter=userName eq "alice@example.com"'
```

A match returns a SCIM `ListResponse` with `totalResults` set to `1`. An unsupported filter or a user that is not visible to the organization returns `totalResults: 0`.

## Test group provisioning

The following request adds an existing Logfire user to the access mapped to the `engineering` group:

```bash
curl --request PATCH "$SCIM_BASE_URL/Groups/engineering" \
  --header "Authorization: Bearer $LOGFIRE_SCIM_TOKEN" \
  --header "Content-Type: application/scim+json" \
  --data '{
    "schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
    "Operations": [
      {
        "op": "Add",
        "path": "members",
        "value": [{"value": "alice@example.com"}]
      }
    ]
  }'
```

Use `"op": "Remove"` with the same `members` path and value shape to remove mapped access. Operation names are case-sensitive and must be exactly `Add` or `Remove`. The path must be exactly `members`; filtered removal paths such as `members[value eq "alice@example.com"]` are not supported. Each member `value` must be an email address for an existing Logfire account. Logfire skips unknown email addresses and continues processing the other members.

After a `204 No Content` response, open **Organization settings → Members** and the relevant project member pages to verify the user's assigned roles. This verification is required during setup because an unsupported patch operation can return `204` without changing access.

## Troubleshooting

### The API returns `401` or `403`

Check that you used an organization API key with the **SCIM provisioning** (`organization:scim`) scope and sent it in the `Authorization` header. Also check that the URL matches your deployment type and region. Enterprise Cloud endpoints reject keys for organizations that are not on an Enterprise plan, even if the scope was available when the key was created. A non-self-hosted deployment rejects requests to the self-hosted route, and a self-hosted deployment rejects managed-provider routes.

### A managed endpoint returns `404` for the identity provider

Check that `{provider_name}` exactly matches the provider name in **Organization settings → Single sign-on**. The identity provider must already exist, and it and the API key must belong to the same organization.

### A user or group query returns no results

Use the exact filter syntax from [Supported operations](#supported-operations). User lookup matches an email address. Group lookup matches a configured group name or ID. In a managed deployment, a discovered user must already belong to the API key's organization.

### A group patch succeeds but a member's access does not change

Check all of the following:

- The group has a mapping in Logfire or the self-hosted deployment configuration.
- The operation is exactly `Add` or `Remove`, its path is exactly `members`, and its `value` is a list of member objects.
- The identity provider is not sending a filtered removal path or replacing membership with `PUT`.
- The member value is the email address of an existing Logfire account.
- The user's current organization role can be changed safely. Logfire preserves required ownership and administrator access.
