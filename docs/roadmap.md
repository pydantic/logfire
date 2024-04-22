---
hide:
- navigation
---

# Roadmap

Here is the roadmap for **Pydantic Logfire**. This is a living document, and it will be updated as we progress.

If you have any questions, or a feature request, **please join our [Slack][slack]**.

## Features 💡

There are a lot of features that we are planning to implement in Logfire. Here are some of them.

### Server side Scrubbing of Sensitive Data

The **Logfire** SDK scrubs sensitive data from logs on the client side before sending them to the server.

We are planning to implement similar scrubbing on the server side for other OpenTelemetry clients.

We'll also support adhoc scrubbing of rows.

### Create Teams

You'll be able to create **teams** with organization.

### Alerts & Notifications

The following features are planned for the alerts and notifications system:

- [ ] Slack integration
- [ ] Email integration
- [X] Webhook integration

Alerts are based on SQL queries (with canned templates for common cases) that are run periodically, and decide if a
new event has occurred.

### Links to GitHub code source

You'll be able to go to your GitHub repository directly from the Logfire UI, and see
the code of a logfire call or exception.

### Cross-Project Dashboards

You'll be able to create dashboards with information from multiple projects.

### On-Premise Deployment

We are planning to offer an on-premise deployment option for Logfire.
This will allow you to deploy Logfire on your own infrastructure.

### Schema Catalog

We want to build a catalog of Pydantic Models/Schemas as outlined
[in our Roadmap article](https://blog.pydantic.dev/blog/2023/06/13/help-us-build-our-roadmap--pydantic/#4-schema-catalog)
with in Logfire.

The idea is that we'd use the SDK to upload the schema of Pydantic models to Logfire.
Then allow you to watch how those schemas change as well as view metrics on how validation performed by a specific model is behaving.

### Language Support

Logfire is built on top of OpenTelemetry, which means that it supports all the languages that OpenTelemetry supports.

Still, we are planning to create custom SDKs for JavaScript, TypeScript, and Rust, and make sure that the
attributes are displayed in a nice way in the Logfire UI — as they are for Python.

### Automatic anomaly detection

We are planning to implement an automatic anomaly detection system, which will be able to detect
anomalies in the logs, and notify you without the need for you to define specific queries.

[slack]: https://join.slack.com/t/pydanticlogfire/shared_invite/zt-2b57ljub4-936siSpHANKxoY4dna7qng
