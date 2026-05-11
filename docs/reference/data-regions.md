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

When you sign up for Logfire at [logfire.pydantic.dev](https://logfire.pydantic.dev) you'll be prompted to choose a region, which sends you to the correct subdomain (either [logfire-us.pydantic.dev](https://logfire-us.pydantic.dev) or [logfire-eu.pydantic.dev](https://logfire-eu.pydantic.dev)). Subsequent logins happen at `logfire-us.pydantic.dev` or `logfire-eu.pydantic.dev`.

![Region picker on the sign-in screen](../images/logfire-screenshot-region-picker.png)

!!! info ""
    We do not detect recent sessions cross-region due to our strict data separation policy for our hosting. So if you open [logfire.pydantic.dev](https://logfire.pydantic.dev) on a new device or in incognito mode, you'll be prompted to pick a region again, even if you already have an account.

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
