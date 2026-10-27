---
title: "Manage saved sandbox snapshots"
description: "Find saved Python state, load it in the Workbench, and delete snapshots you no longer need."
---

# Manage saved snapshots

!!! info "Experimental"
    Agent Sandboxes is available to selected Logfire organizations. See [access and availability](index.md).

Find a saved sandbox state and continue its work, or remove snapshots you no longer need.
A **snapshot** is a saved copy of Python variables, functions, and other interpreter state at one moment.
It does not contain your browser's editor draft or command history.

## Before you start

You need [access to Agent Sandboxes](index.md) and permission to read the project's snapshots.
Deletion also requires permission to manage the project's sandboxes.
Run code in the [Workbench](workbench.md) or save a [Python client session](sessions.md) to create saved state.
Open **AI Optimization** > **Agent Sandboxes** > **Snapshots**.

## Find a saved snapshot

1. Enter part of a snapshot ID or upload ID in **Search snapshots**.
2. Use the status filter to show saved snapshots, uploads, or objects awaiting cleanup.
3. Sort by creation time or size. The **Created** and **Size** column headings also change the sort order.
4. Choose **List view** or **Card view**. Use **Previous** and **Next** to browse more results.

Search and sorting apply across the project inventory, including snapshots on other pages.
The list shows each snapshot's size, creation time, and expiry time.

<img src="/logfire/images/guide/agent-sandboxes/snapshots.webp" alt="Snapshots tab with search, status and sort controls, organization storage, row selection, and Open in Workbench actions" width="1160" height="590" loading="lazy" />

## Open saved state in the Workbench

1. Find a snapshot with **Saved** status.
2. Select **Open in Workbench** on its row or card.
3. Check the selected snapshot in the **Load session** dialog, then select **Load session**.

Opening the Workbench does not restore the snapshot until you confirm the load.
If you already have an open session, choose **Save current and load** to keep its current state first.
Your draft and history stay in this browser. Mounted [volume files](volumes.md) keep their current contents.
See [Load a saved session](workbench.md#load-a-saved-session) for the complete flow.

## Delete snapshots and check storage

!!! warning "Deletion is permanent"
    A deleted snapshot cannot be restored. Existing sessions keep running, but new loads of the deleted snapshot fail.
    Check that you do not need its Python state before you confirm deletion.

For one snapshot, open its **…** menu and select **Delete**.
To delete several, select their checkboxes and choose **Delete selected**.
**Select all on this page** selects only the saved snapshots on the current page.
Review the confirmation before you delete them.

Deletion can show **Cleanup pending** until Logfire removes the stored objects.
The organization storage count and bytes decrease after cleanup finishes.
Pending uploads also count toward storage.
If a bulk deletion partly fails, retry only the snapshots that still show a failure.

The **Organization storage** summary shows the plan allowance and object count across the organization.
Open it to inspect the enforced limit when it differs from the plan allowance.

## Verify

Find a snapshot from your example run and select **Open in Workbench**.
Confirm the load, then read a variable you saved to check that the expected state returns.

## Troubleshooting

- **No snapshots match.** Clear the search and status filter. Check the project, then save a Workbench session if it has no saved state.
- **Load is unavailable.** Uploads and objects awaiting cleanup cannot be loaded. Choose a snapshot with **Saved** status.
- **Storage does not decrease after deletion.** Check for **Cleanup pending**. Storage stays charged until cleanup finishes.
- **A snapshot cannot be restored.** It may have expired, been deleted, or come from an incompatible runtime. Keep your draft and choose another snapshot.

## Next steps

[Run code in the Workbench](workbench.md) to continue from saved state, or [share files between sessions](volumes.md).
