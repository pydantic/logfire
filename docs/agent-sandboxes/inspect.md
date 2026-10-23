---
title: "Inspect sandbox runs"
description: "Use the overview, recorded source, and Live view to investigate sandbox sessions and code runs."
---

# Inspect sandbox runs

Find a sandbox session, read the Python it ran, and follow related activity when a result is slow or fails.
A **session** is a group of related interactions, which can include several code runs and calls.

## Before you start

You need [access to Agent Sandboxes](index.md) and permission to read the project's data.
[Run code in the Workbench](workbench.md) or [connect an application](python.md) so the project has activity to inspect.

## Find a session

1. Open **AI Optimization** > **Agent Sandboxes** > **Overview**.
2. Choose a time range that includes your run. Check any active environment filters.
3. Read the summary cards, then find the session in **Recent invocations**.
4. Check its code-run count, calls, and failures. A missing duration shows **Not reported**, rather than zero.

The cards count **Sessions**, **Code runs**, **Host calls**, **OS calls**, and **Failures** in the selected window.
Host calls are calls from sandbox code back to functions supplied by the client.
OS calls are operating-system operations reported by the runtime.
The overview describes the activity sent to this project, rather than the sandbox's current capacity.

## Read recorded Python source

Select **View code** on the session row.
The dialog lists the code runs with source recorded in the selected time range.
Use the copy control beside a run to copy its source.

<img src="/logfire/images/guide/agent-sandboxes/session-code.webp" alt="Session code dialog with two recorded Python snippets and an Open in Live view link" width="928" height="484" loading="lazy" />

*Example source inspector with sample code.*

!!! warning "Review code before you share it"
    Recorded source can contain application data or credentials that the code includes.
    Check copied source before you paste it into an issue or message.

## Follow related calls in Live view

Select **Open in Live view** in the code dialog, or **Open session in Live view** on the session row.
[Live view](../guides/web-ui/live.md) shows a **trace**, the full journey of one request, made of nested **spans**.
A span is one unit of work: a single operation, with a name, a start, and a duration.
Expand the session to inspect its code runs and related calls.

## Verify

Check that the session and recorded source match the example you ran.
Open it in Live view and confirm that the filter selects the expected activity.

## Troubleshooting

- **The overview is empty.** Widen the time range, check the project and filters, then refresh. An empty view does not prove that execution failed.
- **View code is unavailable or source is missing.** The selected window may lack a session record or source-bearing code runs. Widen it and inspect the related activity in Live view.
- **A row says Activity without session details.** The project received activity without matching session details in this window. Open Live view to inspect the records that are available.
- **A refresh fails.** Use **Retry** and check any warning about stale results before you rely on the displayed counts.

## Next steps

Return to the [Workbench](workbench.md) to reproduce the issue with a smaller input.
