---
title: "SSO Setup (Enterprise Cloud)"
description: "Step-by-step guide to configure Single Sign-On (SSO) for Logfire Enterprise Cloud. Supports Okta, Microsoft Azure Entra ID, Keycloak, and any OIDC-compatible provider."
---

# SSO Setup

Logfire Enterprise Cloud supports Single Sign-On (SSO) via [OIDC-compatible](https://openid.net/developers/how-connect-works/) identity providers, including Okta, Microsoft Azure Entra ID, and Keycloak. Under the hood, Logfire uses [Dex](https://github.com/dexidp/dex), an open-source OIDC gateway.

This guide uses **Microsoft Azure Entra ID** as an example, but the general steps — registering an OIDC app, obtaining a Client ID, Client Secret, and Issuer URL, then connecting it in Logfire — apply to any supported provider.

!!! note "Enterprise Cloud Required"
    SSO is available exclusively on the **Enterprise Cloud** plan. Ensure your organization has Enterprise Cloud enabled before proceeding. [Contact sales](mailto:sales@pydantic.dev) if you need to upgrade.

!!! tip "We Recommend Doing This on a Call"
    SSO configuration involves coordinating between Logfire and your identity provider's admin portal, and it's easy to miss a step. We strongly recommend scheduling a setup call with the Logfire team. Reach out to [support@pydantic.dev](mailto:support@pydantic.dev) to arrange this.

---

## Prerequisites

- **Enterprise Cloud** plan enabled on your Logfire organization
- **Admin access** to your Logfire organization settings
- **Admin access** to Microsoft Azure Entra ID (to create and configure an app registration)

---

## Step 1: Find the Redirect URI in Logfire

1. Log in to Logfire and switch to your **Enterprise Cloud organization**.
2. Go to **Settings** in the left-hand menu.
3. Scroll down to the **Identity Providers** section.
4. Note the **Redirect URI** shown — you will need this when configuring the Azure app.

---

## Step 2: Create an App Registration in Azure Entra ID

1. Sign in to the [Azure portal](https://portal.azure.com) as an admin.
2. Navigate to **Microsoft Entra ID** → **App registrations** → **New registration**.
3. Give the app a name (e.g., `Logfire SSO`).
4. Under **Supported account types**, select the option appropriate for your organization (typically *Accounts in this organizational directory only*).
5. Under **Redirect URI**, choose **Web** (not Single-page application) and paste the Redirect URI copied from Logfire.
6. Click **Register**.

---

## Step 3: Create a Client Secret

1. In your new app registration, go to **Certificates & secrets** → **New client secret**.
2. Add a description and choose an expiry period.
3. Click **Add** and immediately **copy the secret value** — it will not be shown again.

---

## Step 4: Collect Required Values from Azure

From your app registration, gather the following:

| Value | Where to Find It |
|---|---|
| **Client ID** | App registration **Overview** page → *Application (client) ID* |
| **Client Secret** | The value you just created in Step 3 |
| **Tenant ID** | App registration **Overview** page → *Directory (tenant) ID* |

---

## Step 5: Configure the OIDC Provider in Logfire

1. Return to **Logfire** → **Organization Settings** → **Identity Providers**.
2. Click **Add OIDC Provider** and select **Azure** (Microsoft Entra ID).
3. Fill in the fields:
   - **Client ID**: your Azure Client ID
   - **Client Secret**: your Azure Client Secret
   - **Issuer**: `https://login.microsoftonline.com/{tenant-id}/v2.0`
     *(replace `{tenant-id}` with your actual Tenant ID)*
4. Click **Submit**.

---

## Step 6: Connect Entra ID

After submitting, click the **Connect** button next to the Entra ID provider.

A request will be sent to your Azure admin for approval. The Azure admin should approve this in the Entra ID admin center. Once approved, the identity provider status will update to **Linked**.

---

## Step 7: Test the SSO Login

1. Log out of Logfire.
2. Navigate to your organization's SSO login URL:
   ```
   https://logfire.pydantic.dev/{org-name}/login
   ```
   *(replace `{org-name}` with your organization's handle)*
3. Click **Continue with Entra ID** and verify you can log in successfully with your corporate credentials.

---

## Step 8: Invite Team Members

1. Go to your Enterprise Cloud organization in Logfire.
2. Navigate to **Settings** → **Invite Members**.
3. Create an invite link (set it to never expire for convenience if you plan to share it in internal documentation).
4. Share the **invite link** with your team — if users are not already authenticated, it will automatically redirect them to your SSO login page.

---

## Managing Existing Authentication Providers

During the transition, existing login methods (e.g., Google, GitHub) remain active, so current users are not disrupted.

Once your team has successfully migrated to Entra ID SSO:

- You can **disconnect** individual login methods from **Organization Settings** → **Identity Providers**.
- Advise team members to use the SSO login URL going forward. If other providers are still enabled, users may inadvertently log in with their personal accounts instead.

### Linking Accounts for Existing Users

Users who joined the organization before SSO was configured need to connect their existing account to the new identity provider. For example, if a user previously logged in with GitHub and the organization has now set up Azure Entra ID:

1. The user logs in with **GitHub** (their existing provider).
2. They navigate to **Organization Settings** → **Account connections**.
3. They connect their account to **Azure Entra ID**.
4. After linking, the user can log in with either GitHub or Azure.

!!! warning "Existing Users and Email Addresses"
    Users who previously signed up with a different email (e.g., a personal Gmail) will appear with that email in Logfire. To update an email address to a corporate address, the user can go to **Account Settings** → **Emails** (`https://logfire.pydantic.dev/settings/emails`) and add their corporate email.

---

## Summary

| Step | Action |
|---|---|
| 1 | Copy the Redirect URI from Logfire Organization Settings |
| 2 | Create a **Web** app registration in Azure Entra ID with that Redirect URI |
| 3 | Generate a Client Secret in Azure |
| 4 | Collect Client ID, Client Secret, and Tenant ID |
| 5 | Add Azure OIDC provider in Logfire with Issuer URL `https://login.microsoftonline.com/{tenant-id}/v2.0` |
| 6 | Connect Entra ID and approve the request in Azure |
| 7 | Test SSO login via `https://logfire.pydantic.dev/{org-name}/login` |
| 8 | Share the invite link with your team (redirects to SSO login if unauthenticated) |

---

**See also:** [Enterprise Plan Overview](../enterprise.md)
