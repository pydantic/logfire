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

1. [Configure single sign-on](how-to-guides/sso-setup.md), then add the group mappings that assign organization and project roles as described below.
2. In Logfire, go to **Organization settings → API keys**, create an organization API key, and grant it only the **SCIM provisioning** (`organization:scim`) scope. See [Using API Keys to Access Public APIs](reference/advanced/use-api-keys.md).
3. Copy the API key when Logfire displays it. You cannot view it again.

For an Enterprise Cloud deployment, go to **Organization settings → Single sign-on** to find the provider name and manage its group mappings. The identity provider must already exist before its SCIM endpoint is available. The group identifier must exactly match the group name or ID sent by your identity provider.

For a self-hosted deployment, configure group-to-role mappings in the deployment before enabling SCIM. Contact [Logfire support](mailto:support@pydantic.dev) if you need help with the deployment configuration.

## Choose the base URL

Use the base URL for your deployment:

| Deployment | SCIM base URL |
| --- | --- |
| Enterprise Cloud, US region | `https://api-us.pydantic.dev/api/scim/{provider_name}` |
| Enterprise Cloud, EU region | `https://api-eu.pydantic.dev/api/scim/{provider_name}` |
| Enterprise Self-Hosted | `{api_origin}/api/scim` |

For an Enterprise Cloud deployment, replace `{provider_name}` with the exact provider name shown under **Organization settings → Single sign-on**. The provider must belong to the same organization as the API key. For self-hosted deployments, replace `{api_origin}` with the API origin for that deployment.

Send the organization API key as a bearer token with every request:

```http
Authorization: Bearer YOUR_SCIM_API_KEY
```

## Supported operations

| Method and path | Behavior |
| --- | --- |
| `GET /Users?filter=userName eq "email"` | Finds an existing user by email. Enterprise Cloud deployments return only users who already belong to the API key's organization. |
| `GET /Users/{user_email}` | Gets an existing user by email. |
| `GET /Groups?filter=displayName eq "group"` | Finds a configured group mapping by its exact group name or ID. |
| `GET /Groups/{group_id}` | Gets a configured group mapping. |
| `PATCH /Groups/{group_id}` | Applies `add` or `remove` operations to the mapping's members and returns `204 No Content`. |

The collection endpoints support only the filters shown in the table, including the exact attribute name, spacing, and double quotes. Compound filters are not supported. They return at most one resource. Group responses describe the mapped group but do not list its current members.

The API does not support `POST`, `PUT`, or `DELETE` operations for users or groups. It also does not expose `/ServiceProviderConfig`, `/ResourceTypes`, or `/Schemas`. Groups and users must already exist, so do not enable identity-provider actions that create or manage their lifecycle.

!!! note "Self-hosted deployments"
    This page describes the current group patch contract: case-insensitive operation and path names, filtered single-member removal paths, and rejection of an unsupported patch with `400`. An Enterprise Self-Hosted deployment runs the [Logfire Helm chart](https://github.com/pydantic/logfire-helm-chart) version you installed, so an older installation can still apply the earlier behavior, which accepted only `Add` and `Remove` with an exact `members` path and returned `204` for an operation it did not apply. If your deployment behaves that way, upgrade the chart or contact [Logfire support](mailto:support@pydantic.dev) to confirm the version you need. Enterprise Cloud always runs the current behavior.

## Choose a compatible identity-provider setup

The current interface is designed for existing-user discovery and group-membership changes, not a provider's default end-to-end SCIM lifecycle flow. Compatibility depends on two separate things: whether the provider's group-membership requests match this API, and whether the provider can finish connecting to an application that implements only this subset. A provider whose membership requests fit can still fail earlier, while it sets up the connection.

- **Microsoft Entra ID:** The request shape of [Entra's group-member add and remove requests](https://learn.microsoft.com/en-us/entra/identity/app-provisioning/use-scim-to-provision-users-and-groups#update-group-add-members) matches the documented `PATCH /Groups/{group_id}` format. Entra fills each `members[].value` with the SCIM `id` it recorded for the user when it provisioned or matched that user, which by default is the identifier your application returned rather than an email address. Logfire requires an email address there and silently skips any other value, so membership changes only apply when Entra's stored `id` for each user is that user's Logfire email address. Note that Logfire does not meet several of [Entra's stated SCIM requirements](https://learn.microsoft.com/en-us/entra/identity/app-provisioning/use-scim-to-provision-users-and-groups#scim-protocol-requirements), including user creation and the `/Schemas` endpoint that Entra requests when you save a provisioning configuration. Entra treats schema discovery as a way to add target attributes rather than a prerequisite, so a custom non-gallery application can still save, but verify that the provisioning job saves and runs in your tenant before relying on it. Configure provisioning to use only existing Logfire users and existing group mappings, and contact [Logfire support](mailto:support@pydantic.dev) if setup does not complete or the values Entra sends are object IDs.
- **Okta:** [Okta Group Push](https://developer.okta.com/docs/api/openapi/okta-scim/guides/scim-20/#update-specific-group-membership) cannot complete setup against this endpoint, even though its membership requests are compatible. Okta sends lowercase operation names and filtered member-removal paths such as `members[value eq "alice@example.com"]`, both of which Logfire accepts. However, enabling provisioning makes Okta send unfiltered paginated requests such as `GET /Users?startIndex=1&count=2` and `GET /Groups?startIndex=1&count=100`, and Group Push creates the group with `POST /Groups`. Logfire supports only the exact filters in [Supported operations](#supported-operations) and does not support `POST`, so Okta fails before it sends any membership patch. Use [SSO group mappings](how-to-guides/sso-setup.md) to apply access when users sign in, or contact [Logfire support](mailto:support@pydantic.dev).

For another identity provider, check both things before enabling provisioning: that its group-membership request format matches [Supported operations](#supported-operations), and that it can connect without the endpoints listed above as unsupported. A provider can also report success for a member value that is not the email address of an existing Logfire account, because Logfire skips unknown addresses by design, so verify the resulting roles in Logfire during setup.

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
        "op": "add",
        "path": "members",
        "value": [{"value": "alice@example.com"}]
      }
    ]
  }'
```

Use `"op": "remove"` with the same `members` path and value shape to remove mapped access. Operation and path names are case-insensitive, so `add`, `Add`, `members`, and `Members` are all accepted. To remove a single member, you can also send a filtered path such as `"path": "members[value eq \"alice@example.com\"]"`, the form Okta Group Push uses. Each member `value` must be an email address for an existing Logfire account. Logfire skips unknown email addresses and continues processing the other members.

Logfire validates the whole patch before applying any of it. An unsupported `op`, an unsupported or missing `path`, or a `value` that is not a list returns `400 Bad Request` with a message naming the offending operation, and no part of the patch is applied.

After a `204 No Content` response, open **Organization settings → Members** and the relevant project member pages to verify the user's assigned roles. Confirming the roles during setup shows that the member values your provider sends resolve to the Logfire accounts you expect.

## Troubleshooting

### The API returns `401` or `403`

Check that you used an organization API key with the **SCIM provisioning** (`organization:scim`) scope and sent it in the `Authorization` header. Also check that the URL matches your deployment type and region. Enterprise Cloud endpoints reject keys for organizations that are not on an Enterprise plan, even if the scope was available when the key was created. A non-self-hosted deployment rejects requests to the self-hosted route, and a self-hosted deployment rejects managed-provider routes.

### An Enterprise Cloud endpoint returns `404` for the identity provider

Check that `{provider_name}` exactly matches the provider name in **Organization settings → Single sign-on**. The identity provider must already exist, and it and the API key must belong to the same organization.

### A user or group query returns no results

Use the exact filter syntax from [Supported operations](#supported-operations). User lookup matches an email address. Group lookup matches a configured group name or ID. In an Enterprise Cloud deployment, a discovered user must already belong to the API key's organization.

### The identity provider cannot save or test the connection

A provider that runs its own connection test or import step can fail before it sends any membership patch, because Logfire implements only the subset in [Supported operations](#supported-operations). Providers commonly probe with unfiltered or paginated `GET /Users` and `GET /Groups` requests, create groups with `POST /Groups`, or read `/ServiceProviderConfig`, `/ResourceTypes`, or `/Schemas`, none of which Logfire supports. See [Choose a compatible identity-provider setup](#choose-a-compatible-identity-provider-setup) for the providers this affects, and use [SSO group mappings](how-to-guides/sso-setup.md) or contact [Logfire support](mailto:support@pydantic.dev) if your provider cannot connect.

### A group patch returns `400`

Logfire rejects a patch that contains an operation it does not support, and the response message names the offending operation. Check that each operation's `op` is `add` or `remove`, that it has a `path` of `members` or a filtered `members[value eq "..."]` path, and that any `value` is a list of member objects. Because Logfire validates the whole patch first, one bad operation prevents the others from applying, so fix the named operation and send the patch again.

### A group patch succeeds but a member's access does not change

Check all of the following:

- The group has a mapping in Logfire or the self-hosted deployment configuration.
- The member value is the email address of an existing Logfire account, not an identity-provider object ID or another identifier. Unknown addresses are skipped without failing the request.
- The identity provider is not replacing membership with `PUT`, which Logfire does not support.
- The user's current organization role can be changed safely. Logfire preserves required ownership and administrator access.
