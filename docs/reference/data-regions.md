---
title: "Logfire Data Regions: Choose Your Storage Location"
description: Select your data region for Logfire. Logfire offers separate US and EU regions for optimal performance and to meet data compliance and residency needs.
---
# Data Regions

Logfire is hosted in two separate geographic regions to provide you with options for data residency, compliance with local regulations, and optimal performance.

## Available Regions

|              | Hosted           | URL                                                         |
|--------------|------------------|-------------------------------------------------------------|
| 🇺🇸 US Region | GCP us-east4     | [logfire-us.pydantic.dev](https://logfire-us.pydantic.dev)  |
| 🇪🇺 EU Region | GCP europe-west4 | [logfire-eu.pydantic.dev](https://logfire-eu.pydantic.dev)  |

## Region Separation

Regions are strictly separated with no data sharing between them:

* No data is transferred between regions
* No cookies are shared between regions
* Authentication tokens are region-specific
* User accounts are separate for each region

## Choosing a Region

Logfire is a regional product: every account, project, and trace lives in exactly one region, and the URL you visit determines which region you're working with. There is no cross-region landing page — visiting [logfire.pydantic.dev](https://logfire.pydantic.dev) sends you straight to the US region's sign-in screen, where you'll see a region picker:

![Region picker on the sign-in screen](../images/logfire-screenshot-region-picker.png)

* **First-time visitors** must pick a region before continuing — there is no default.
* **Returning users** see their last-used region pre-selected. Picking a different region redirects you to that region's subdomain ([logfire-us.pydantic.dev](https://logfire-us.pydantic.dev) or [logfire-eu.pydantic.dev](https://logfire-eu.pydantic.dev)); picking the same region keeps you where you are.

If you already know which region your account lives in, you can also navigate directly to its subdomain and skip the picker.

Consider the following factors when selecting a region:

* **Geographic proximity**: Choose a region closer to your location or your users for optimal performance
* **Data residency requirements**: Select the region that aligns with your regulatory compliance needs
* **GDPR compliance**: Companies requiring GDPR compliance are advised to use the EU region

## Multiple Regions

You can have accounts in both regions if needed for different projects or teams. Each account is managed separately, with its own authentication and data.

## Region Migration

Migration between regions is not currently available but we hope to make it possible in the future.

## How does this Impact Pricing?
Pricing is the same between the US and EU instances.

## Region URLs

Always ensure you're using the correct region-specific URL:

* US: [logfire-us.pydantic.dev](https://logfire-us.pydantic.dev)
* EU: [logfire-eu.pydantic.dev](https://logfire-eu.pydantic.dev)

The global domain ([logfire.pydantic.dev](https://logfire.pydantic.dev)) is a convenience entry point only — it redirects to the US region, where the sign-in screen's region picker lets you switch to EU if needed. It is not a separate region and holds no data.
