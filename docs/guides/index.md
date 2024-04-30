Here are some tutorials to help you get started using Logfire:

## **First Steps**
In [this guide](first_steps/index.md), we walk you through installation and authentication in your local environment, sending a log message
to Logfire, and viewing it in the Logfire Web UI.

## **Onboarding Checklist 📋**
In [this guide](onboarding_checklist/index.md), we provide a checklist with step-by-step instructions to take an existing application and thoroughly
instrument it to send data to Logfire. In particular, we'll show you how to leverage Logfire's various
[integrations](../integrations/index.md) to generate as much useful data with as little development effort as possible.

**Following this checklist for your application is _critical_ to getting the most out of Logfire.**

## **Intro to the Web UI**
In [this guide](web_ui/index.md), we introduce the various views and features of the Logfire Web UI, and show you how to use them
to investigate your projects' data.

[//]: # (When we have more than one, I think it's worth adding the following section:)
[//]: # (### Use cases)
[//]: # ()
[//]: # (We have special documentation for some common use cases:)
[//]: # (* **[Web Frameworks]&#40;use_cases/web_frameworks.md&#41;:** Django, Flask, FastAPI, etc.)

[//]: # (Once we have more content, I think this would also be a useful section, somewhat different than the previous:)
[//]: # (### Case Studies)
[//]: # (* **[Investigating database performance issues with the Live view]&#40;...&#41;** [autoexplain + pgmustard])
[//]: # (* **[Monitoring deployment health]&#40;...&#41;** [dashboards + alerts])
[//]: # (* **[Investigating your data with the Live and Explore views]&#40;...&#41;**)


## **Advanced User Guide**

We cover additional topics in the **[Advanced User Guide](advanced/index.md)**, including:

* **[Sampling](advanced/sampling.md/#sampling):** Down-sample lower-priority traces to reduce costs.
* **[Scrubbing](advanced/scrubbing.md):** Remove sensitive data from your logs and traces before sending them to Logfire.
* **[Testing](advanced/testing.md):** Test your usage of Logfire.
* **[Direct Database Connections](advanced/direct_database_connections.md):** Connect directly to a read-only postgres
database containing your project's data. You can use this for ad-hoc querying, or with third-party
business intelligence tools like Grafana, Tableau, Metabase, etc.
* ... and more.

## **Integrations and Reference**

* **[Integrations](../integrations/index.md):**
In this section of the docs we explain what an OpenTelemetry instrumentation is, and offer detailed guidance about how
to get the most out of them in combination with Logfire. We also document here how to send data to Logfire from other
logging libraries you might already be using, including `loguru`, `structlog`, and the Python standard library's
`logging` module.
* **[Configuration](../reference/configuration.md):**
In this section we document the various ways you can configure which Logfire project your deployment will send data to.
* **[Organization Structure](../reference/organization_structure.md):**
In this section we document the organization, project, and permissions model in Logfire.
* **[SDK CLI docs](../reference/cli.md):**
Documentation of the `logfire` command-line interface.
