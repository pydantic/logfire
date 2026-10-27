---
title: "Share files between sandbox sessions"
description: "Create a hosted volume and mount it in a profile so sandbox sessions can share files."
---

# Share files between sessions

!!! info "Experimental"
    Hosted volumes require separate enablement for your organization. If you do not see **Volumes** or **Mounts**, this feature is not enabled.

Keep files between sandbox sessions and share them with sessions that use the same profile.
A **volume** stores files separately from Python memory.
A **mount** gives a profile access to a volume at a path such as `/data`.

## Before you start

You need [access to Agent Sandboxes](index.md), volume access, and permission to manage the project's volumes and profiles.
[Create a profile](profiles.md) such as `Analysis` before you add a mount.

## Create and mount a volume

1. Open **AI Optimization** > **Agent Sandboxes** > **Volumes**.
2. Select **Create volume**, enter a **Volume name** such as `Shared reports`, then select **Create volume**.
3. Open **Profiles** and select **Mounts** beside `Analysis`.
4. Choose `Shared reports` under **Volume** and enter `/data` under **Mount path**.
5. Choose **Read and write** under **Access**, then select **Mount volume**.

<img src="/logfire/images/guide/agent-sandboxes/profile-mounts.webp" alt="Profile volumes dialog with Shared reports mounted at /data with Read and write access" width="512" height="495" loading="lazy" />

Use **Read only** when a session should read files without changing them.
Use **Search volumes** and the sort control to find a volume by name in a longer list.

## Write and read a shared file

Close the mount dialog and select **Use profile** beside `Analysis`.
In the Workbench, run:

```python skip-run="true" skip-reason="sandbox-code"
from pathlib import Path

Path('/data/shared.txt').write_text('shared volume bytes')
```

The result is `19`, the number of characters written.
Then run:

```python skip-run="true" skip-reason="sandbox-code"
from pathlib import Path

Path('/data/shared.txt').read_text()
```

The result is `'shared volume bytes'`.
Other sessions that use this profile can read the same file.

!!! warning "Snapshots do not roll back files"
    A snapshot saves Python state. Volume files keep their current contents when you load that snapshot.
    Use separate files or an application backup when you need an earlier version of a file.

## Change or remove access

Open **Profiles** > **Mounts** again.
Select **Edit mount**, change the path or access, then select **Save changes**.
Changes apply when the profile next accesses a volume.
Select **Unmount** to remove the profile's access without deleting the volume's files.

!!! warning "Volume deletion is permanent"
    Deleting a volume removes its files. A Python snapshot cannot recover them.
    Copy any files you need before you delete the volume.

To delete the stored files, open the volume's **…** menu in **Volumes** and select **Delete volume**.
Check the name in the confirmation before you continue.

## Verify

Check that the profile's mount list shows `/data` with **Read and write** access.
Run the write and read examples, then read the file from a new session with the same profile.
It should return `'shared volume bytes'`.

## Troubleshooting

- **Volumes or Mounts is missing.** Volume access is not enabled for the organization, or your account lacks access to the project.
- **A write fails.** Check that the session uses the correct profile and that the mount allows **Read and write** access.
- **A file is missing.** Check the mount path. An unmounted or deleted volume is unavailable to the session.

## Next steps

[Manage profiles](profiles.md) to control which sessions share files, or [manage saved snapshots](snapshots.md) to restore Python state.
