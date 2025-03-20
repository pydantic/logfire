# Data Regions

Logfire is hosted in two separate geographic regions to provide you with options for data residency, compliance with local regulations, and optimal performance.

## Available Regions

* 🇺🇸 **US Region**: [logfire-us.pydantic.dev](https://logfire-us.pydantic.dev) - Hosted in GCP us-east4
* 🇪🇺 **EU Region**: [logfire-eu.pydantic.dev](https://logfire-eu.pydantic.dev) - Hosted in GCP europe-west4

## Region Separation

Regions are strictly separated with no data sharing between them:

* No data is transferred between regions
* No cookies are shared between regions
* Authentication tokens are region-specific
* User accounts are separate for each region

## Choosing a Region

When you sign up for Logfire, you'll be prompted to choose a region. After selecting your region, you'll be automatically redirected from the global domain (logfire.pydantic.dev) to your region-specific domain (either logfire-us.pydantic.dev or logfire-eu.pydantic.dev).

Consider the following factors when selecting a region:

* **Geographic proximity**: Choose a region closer to your location or your users for optimal performance
* **Data residency requirements**: Select the region that aligns with your regulatory compliance needs
* **GDPR compliance**: Companies requiring GDPR compliance may prefer the EU region

## Multiple Regions

You can maintain accounts in both regions if needed for different projects or teams. Each account is managed separately, with its own authentication and data.

## Region Migration

Migration between regions is not currently available. We're working on implementing region migration functionality and expect to make it available soon.

## Region URLs

Always ensure you're using the correct region-specific URL:
* US region: [logfire-us.pydantic.dev](https://logfire-us.pydantic.dev)
* EU region: [logfire-eu.pydantic.dev](https://logfire-eu.pydantic.dev)

The global domain (logfire.pydantic.dev) is used primarily for the initial signup process where you'll select your region.