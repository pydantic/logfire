---
title: "Run code in the Workbench"
description: "Run Python interactively, check types, and save or restore sandbox sessions in the Workbench."
---

# Run code in the Workbench

!!! info "Experimental"
    Agent Sandboxes is available to selected Logfire organizations. See [access and availability](index.md).

Try Python in your project's sandbox and read the result without installing a client.
Each submission runs in the same session until you reset it or load another saved session.
A **session** is a group of related interactions, which here can share Python variables.

## Before you start

You need [access to Agent Sandboxes](index.md) and permission to run code in the project.
Open **AI Optimization** > **Agent Sandboxes** > **Workbench**.
If the project shows **Enable Agent Sandboxes**, ask a project manager to enable it first.
If you want a named profile, [create one](profiles.md) before you start the session.
Check [what sandbox code can do](limits.md) if your code uses imports or features beyond the examples below.

!!! warning "Code runs on Logfire Cloud"
    Your submission leaves the browser and runs in a remote sandbox.
    Recorded activity can include your source and output. Use sample data and keep credentials out of the code.
    Saved checkpoints also contain Python variables and computed values. See [session storage](sessions.md#what-is-saved).

## Run an expression

1. If the **Profile** selector is available, choose a profile or **No profile**.
2. Enter this expression in the Python editor:

    ```python
    sum([12, 18, 30])
    ```

3. Select **Run code**. You can also press **⌘+Enter** on macOS, **Ctrl+Enter** on Windows and Linux, or **Shift+Enter**.
4. Read the result below the editor. The expression returns `60`.

## Reuse a variable and review history

Run this code, then submit `total` as a separate run:

```python
total = 42
print('Saved total')
#> Saved total
```

The first run prints `Saved total`. The second returns `42`.
After a successful run, the Workbench clears the editor for the next command.
The transcript shows the newest run first, with its execution time, result, printed output, or Python error.

<img src="/logfire/images/guide/agent-sandboxes/workbench-history.webp" alt="Workbench with Type check, Load session, Save session, a Saved here marker, and total returning 42" width="1160" height="485" loading="lazy" />

*A saved checkpoint includes the variables from the completed run.*

Select **History** to find an earlier command and load it into the editor.
Loading a command does not run it. Review it before you select **Run code**.
Use **Examples** to load a sample instead.
Press **Alt+↑** or **Alt+↓** in the editor to recall commands.
For long output, select **Show more**. The copy control copies the full output, including text hidden by **Show less**.

## Check types before execution

Select **Type check** beside **Run code** to check the submitted code before it executes.
For example, `total: int = 'wrong'` reports an assignment error instead of changing `total`.
The rejected code stays in the editor so you can fix it.
The setting stays selected for later runs. Changing it does not reset the session.

## Continue after a reload

The Workbench automatically saves Python state after completed runs.
You can also select **Save session** before you leave.
Wait for **Saved at** and the **Saved here** marker before you rely on that checkpoint.

The browser keeps your draft and up to 50 finished runs for the current account, project, and profile.
Reloading or returning to the page restores this local history.
The Workbench does not execute the old code again.

1. Reload the page or return to the Workbench.
2. Select **Continue session** to restore the saved Python state.
3. Run `total`. It returns `42` if your checkpoint includes the assignment above.

<img src="/logfire/images/guide/agent-sandboxes/workbench-continue.webp" alt="Workbench after a reload with Session saved, Continue session, and Run code disabled until continuation" width="1200" height="510" loading="lazy" />

**Run code** stays unavailable until continuation succeeds or you reset the session.
Another browser does not inherit this browser's draft or history.
To restore a saved Python state there, use **Load session**.

## Load a saved session

1. Choose the profile whose current volume access the session should use, or **No profile**.
   If the selector is locked, use **Switch profile** first.
2. Select **Load session** beside **Save session**.
3. Search for the saved snapshot by its ID, then select it.
4. Select **Load session** in the dialog.

<img src="/logfire/images/guide/agent-sandboxes/load-session.webp" alt="Load session dialog with searchable saved snapshots, the selected profile, and a Load session button" width="672" height="622" loading="lazy" />

If a session is already open, choose **Save current and load** to keep a checkpoint before you replace its Python state.
Choose **Load without saving** only if you do not need the current state.
If the save fails, the Workbench stops the load so you can retry.

A snapshot restores Python variables and functions. It does not replace your browser draft or history.
Mounted [volume files](volumes.md) keep their current contents.
You can also start this flow from **Open in Workbench** on the [Snapshots](snapshots.md) tab.

## Start a fresh session

To clear the variables, transcript, and local continuation, open **Reset session**, then confirm **Reset session**.
You cannot undo this reset. Your editor code and saved snapshots stay unchanged.
Use the [Snapshots](snapshots.md) tab to delete saved Python state from server storage.
To choose another profile during a session, select **Switch profile** and confirm **End session and switch profile**.
Each profile has its own browser draft and history. Save any state you need before you switch.

## Verify

Check that the sum returns `60` and that `total` returns `42` in the same connected session.
Reload, select **Continue session**, and run `total` again to check your saved state.
Use [Overview](inspect.md) to inspect recorded activity after a run.

## Troubleshooting

- **Run code is unavailable.** Check the displayed connection or permission message. Retry after the sandbox becomes available.
- **A variable is missing.** Check whether you continued the right checkpoint and selected the right profile. A reset starts with no variables.
- **Saving or continuation fails.** Keep the draft and retry the failed action. A failed save keeps the previous checkpoint. A deleted or expired snapshot cannot be restored.
- **The connection fails after submission.** The code may have run without a result reaching the browser. Inspect activity before you repeat code with side effects.

## Next steps

[Connect an application](python.md) to submit code from your own program.
