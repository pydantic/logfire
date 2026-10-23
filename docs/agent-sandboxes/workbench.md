---
title: "Run code in the Workbench"
description: "Run Python interactively, reuse variables within a connected session, and review the Workbench history."
---

# Run code in the Workbench

!!! info "Experimental"
    Agent Sandboxes is available to selected Logfire organizations. See [access and availability](index.md).

Try Python in your project's sandbox and read the result without installing a client.
Each submission runs in the same session while the connection stays open.
A **session** is a group of related interactions, which here can share Python variables.

## Before you start

You need [access to Agent Sandboxes](index.md) and permission to run code in the project.
Open **AI Optimization** > **Agent Sandboxes** > **Workbench**.
If you want a named profile, [create one](profiles.md) before you start the session.
Check [what sandbox code can do](limits.md) if your code uses imports or features beyond the examples below.

!!! warning "Code runs on Logfire Cloud"
    Your submission leaves the browser and runs in a remote sandbox.
    Recorded activity can include your source and output. Use sample data and keep credentials out of the code.

## Run an expression

1. If the **Profile** selector is available, choose a profile or **No profile**.
2. Enter this expression in the Python editor:

    ```python
    sum([12, 18, 30])
    ```

3. Select **Run code**. You can also press **⌘+Enter** on macOS or **Ctrl+Enter** on Windows and Linux.
4. Read the result below the editor. The expression returns `60`.

## Reuse a variable and review history

Run this code, then submit `total` as a separate run:

```python
total = 42
print('Saved total')
#> Saved total
```

The first run prints `Saved total`. The second returns `42` while the session stays connected.
The transcript shows the newest run first, including results, printed output, and Python errors.

<img src="/logfire/images/guide/agent-sandboxes/workbench-history.webp" alt="Workbench transcript with a saved total, a result of 42, and a division-by-zero error" width="1280" height="600" loading="lazy" />

*Sample history shows a successful run and a Python error.*

Select **History** to find an earlier command and load it into the editor.
Loading a command does not run it. Review it before you select **Run code**.
Use **Examples** to load a sample instead.

## Start a fresh session

The Workbench keeps the latest 50 finished runs during your visit.
Leaving the page or reloading clears this transcript.
The connection also closes after a period of inactivity. A later connection starts a new session.
Do not rely on variables surviving a disconnect.

Workbench sessions are **ephemeral**. Logfire does not save their Python state for you to restore later.
Application sessions can persist across connections. See [Persist, resume, and fork sessions](sessions.md) for that workflow.

To clear the variables and transcript, open **Reset session**, then confirm the reset.
You cannot undo this reset. Your editor code stays unchanged.
To choose another profile during a session, select **Switch profile** and confirm **End session and switch profile**.
This clears the session variables. Your code and transcript stay unchanged.

## Verify

Check that the sum returns `60` and that `total` returns `42` in the same connected session.
Use [Overview](inspect.md) to inspect recorded activity after a run.

## Troubleshooting

- **Run code is unavailable.** Check the displayed connection or permission message. Retry after the sandbox becomes available.
- **A variable is missing.** The previous session may have ended. Run the assignment again in the current session.
- **The connection fails after submission.** The code may have run without a result reaching the browser. Inspect activity before you repeat code with side effects.

## Next steps

[Connect an application](python.md) to submit code from your own program.
