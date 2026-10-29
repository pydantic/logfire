---
title: "Inspect sandbox runs"
description: "Use the overview, recorded source, and Live view to investigate sandbox sessions and code runs."
---

# Inspect sandbox runs

!!! info "Experimental"
    Agent Sandboxes is available to selected Logfire organizations. See [access and availability](index.md).

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
The overview shows hosted sandbox activity from the `monty-worker` service.
It does not include every locally instrumented Monty client or show the sandbox's current capacity.

## Read recorded Python source

Select **View code** on the session row.
The dialog lists the code runs with source recorded in the selected time range.
Use the copy control beside a run to copy its source.

<img src="/logfire/images/guide/agent-sandboxes/session-code.webp" alt="Session code dialog with the recorded print and total commands and an Open in Live view link" width="896" height="317" loading="lazy" />

*Example source inspector with sample code.*

!!! warning "Review code before you share it"
    Recorded source can contain application data or credentials that the code includes.
    Check copied source before you paste it into an issue or message.

## Follow related calls in Live view

Select **Open in Live view** in the code dialog, or **Open session in Live view** on the session row.
[Live view](../guides/web-ui/live.md) shows a **trace**, the full journey of one request, made of nested **spans**.
A span is one unit of work: a single operation, with a name, a start, and a duration.
Expand the session to inspect its code runs and related calls.

## Step through function calls

Select a **run code** span in Live view, then open its **Code** tab.
For a run with recorded function calls, **Source** shows the Python code and a timeline of those calls.

1. Select **Step over** to move to the next recorded call, or **Step back** to return to the previous one.
2. Read **Call attributes** for the function, arguments, duration, and source location under **Called from**.
3. Read **Return value** for the selected call's result.

The source highlights the selected call and shows its return value beside the expression.
The trace list highlights the same call while the **run code** span stays selected.
You can also choose a call with the **Run timeline** slider or a source gutter marker.

<img src="/logfire/images/guide/agent-sandboxes/call-stepper.webp" alt="Code tab on the second get_weather call, with New York as the argument, its source highlighted, and a return value of 24 degrees Celsius" width="838" height="560" loading="lazy" />

*Two calls on the same source line have separate arguments, return values, and timings.*

Scroll below the call inspector to read **Result** for the whole run and **Arguments** for its inputs.
These differ from the selected function call's arguments and return value.
Printed text appears in related **print stdout** records in the trace list.

## Verify

Check that the session and recorded source match the example you ran.
Open it in Live view. Confirm that its code runs and related calls match the source shown in the code dialog.
For a run with several function calls, step between them and check that their arguments and return values change.

## Troubleshooting

- **The overview is empty.** Widen the time range, check the project and filters, then refresh. Locally instrumented Monty activity appears in Live view but is outside this hosted overview.
- **View code is unavailable or source is missing.** The selected window may lack a session record or source-bearing code runs. Widen it and inspect the related activity in Live view.
- **A row says Activity without session details.** The project received activity without matching session details in this window. Open Live view to inspect the records that are available.
- **A call is missing from the timeline.** Load more spans in the trace list. The inspector uses the calls that the list has loaded. A `+` after the call count means more calls may exist.

## Next steps

Return to the [Workbench](workbench.md) to reproduce the issue with a smaller input.
