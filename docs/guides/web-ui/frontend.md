---
title: "Frontend"
description: "Find slow pages, browser errors, heavy resources, and user sessions from frontend telemetry in Logfire."
---
# Frontend

Use the <OpenInLogfire path="frontend" variant="inline" label="Frontend" /> page to find slow pages, browser errors, and the resources or API calls affecting real users.

The page groups browser telemetry by frontend application. A frontend application gives browser data a stable service name and a restricted token that is safe to publish in a browser bundle. The token can send data only for that application. It cannot read project data or report as another service.

!!! note "Experimental"

    Open **Settings → Early access**, choose **Show experimental features**, and enable **Frontend observability**. This browser-level setting applies across every organization you use in that browser.

## Send browser data

1. Open **Project settings → Frontend applications**.
2. Select **New application** and give the application a stable name, such as `customer-portal`.
3. Copy the generated setup into your browser application.
4. Enable the browser signals you want to investigate. See the [browser SDK guide](https://pydantic.dev/docs/logfire/instrument/typescript/packages/browser/) for automatic request tracing, Core Web Vitals, browser metrics, and framework-specific options.

Browser telemetry is sent to and stored in your Logfire project. Review the attributes your application adds before sending sensitive values.

## Find what affects users

Select a time range and, when a project has several frontend applications, choose one application or keep **All applications** selected. You can filter the results by page, domain, country, browser, operating system, or device.

The page combines several views of the same browser activity:

- **Page loads** and load-time summaries show traffic and the latency users experienced.
- **Core Web Vitals** show loading, responsiveness, and visual-stability measurements from real page loads. The default p75 view reports the 75th percentile, so 75% of observations are at or below the displayed value.
- **What's slow** identifies page elements and interactions associated with poor results.
- **Top pages**, **Largest resources**, and **Slowest API calls** help connect a slow experience to a route, asset, or request.
- **Top errors** links browser failures to the matching records in Live view.

When you filter to an investigation target, Logfire also shows related recorded sessions when a [session replay](session-replays.md) is available.

## Verify browser data

Load an instrumented page, interact with it, and return to **Frontend**. Expand the time range if needed. You should see a page load and the application's name. Core Web Vitals appear only after you enable `rum.webVitals` and supported browsers report measurements.

## Fix missing frontend data

| Symptom | What to check |
|---------|---------------|
| **No frontend data in this range** | Confirm the generated browser setup is running, the token belongs to the selected application, and the time range includes a recent page load. |
| The application is missing | Select **All applications**, then confirm the application still exists under **Project settings → Frontend applications**. |
| Page loads appear without Core Web Vitals | Enable `rum.webVitals` in the browser SDK configuration, reload the page, and wait for supported measurements to complete. |
| Requests fail from the browser | Check the browser network panel for authentication, content-security-policy, or ad-blocker failures. |
