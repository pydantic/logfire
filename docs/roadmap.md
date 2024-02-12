---
hide:
- navigation
---

# Roadmap

Here is the roadmap for **Logfire**. This is a living document, and it will be updated as we progress.

If you have any questions, or a feature request, **please join our [Slack][slack]**.

## Features 💡

There are a lot of features that we are planning to implement in Logfire. Here are some of them.

### Client and Server side Scrubbing of Sensitive Data

We are planning to implement a system that will scrub sensitive data from the logs, both on the client and server side.

### Create Organizations & Teams

You'll be able to create a **new separate organization**, and invite others.

Also, on the same line, you'll be able to create **teams** on the organization.

### Alerts & Notifications

The following features are planned for the alerts and notifications system.

- Slack integration
- Email integration
- Webhook integration

### Links to GitHub code source

You'll be able to go to your GitHub repository directly from the Logfire UI, and see
the code from which the logs are coming from.

### Cross-Project Dashboards

You'll be able to create dashboards with information from multiple projects.

### Direct connection to Postgres

You'll be able to connect to our Postgres database directly from your local machine, and
query Logfire data directly from your local machine.

### Language Support

Logfire is built on top of OpenTelemetry, which means that it supports all the languages that OpenTelemetry supports.

Still, we are planning to create custom SDKs for JavaScript, TypeScript, and Rust, and make sure that the
attributes are displayed in a nice way in the Logfire UI.

### Automatic anomaly detection

We are planning to implement an automatic anomaly detection system, which will be able to detect
anomalies in the logs, and notify you about them.

### Enable Anonymous Projects

You'll be able to create a project without an account, and start sending logs to Logfire.

[slack]: https://join.slack.com/t/pydanticlogfire/shared_invite/zt-2b57ljub4-936siSpHANKxoY4dna7qng
