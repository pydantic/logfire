---
title: "Manage sandbox profiles"
description: "Create, select, rename, and delete project profiles for Agent Sandboxes."
---

# Manage sandbox profiles

Give sandbox sessions a stable, named profile that you can select when you run code.
A profile belongs to one project and has its own ID.
A **session** is a group of related interactions, such as successive Workbench code runs.

## Before you start

You need [access to Agent Sandboxes](index.md) and permission to manage profiles in the project.
Members with read-only access can inspect the list but cannot change it.
Open **AI Optimization** > **Agent Sandboxes** > **Profiles**.

## Create a profile

1. Select **Create profile**.
2. Enter a **Profile name**, such as `Analysis`.
3. Select **Save profile**.

<img src="/logfire/images/guide/agent-sandboxes/create-profile.webp" alt="Create profile dialog with Analysis entered as the profile name" width="544" height="254" loading="lazy" />

*Example profile name.*

The list shows the profile name and ID after the save succeeds.
Use **Previous** and **Next** if the list spans several pages.

## Use a profile in the Workbench

Select **Use profile** beside the profile to open the Workbench with it selected.
You can also choose it from the Workbench's **Profile** selector before the session starts.

<img src="/logfire/images/guide/agent-sandboxes/profiles.webp" alt="Profiles tab with the Analysis profile, its ID, and Use profile, Rename, and Delete actions" width="1280" height="288" loading="lazy" />

*Example list with one profile.*

Once a session starts, its profile selection stays fixed.
To choose another, select **Switch profile** and confirm **End session and switch profile**.
This clears the session variables. Your code and transcript stay unchanged.
Selecting a profile does not restore a previous Workbench transcript or guarantee that Python variables persist across sessions.

## Rename or delete a profile

Select **Rename**, update **Profile name**, then select **Save profile**.
Renaming preserves the profile ID, so callers that use that ID keep the same profile identity.

!!! warning "Deletion prevents future use"
    After you delete a profile, new sessions and recovered sessions can no longer use it.
    Creating another profile with the same name gives it a different ID.
    Update callers that use the old ID before you delete the profile.

To delete a profile, select **Delete**, check the name in the confirmation, then select **Delete profile**.

## Verify

Find the saved name and ID in **Profiles**.
Select **Use profile** and check that the Workbench selects that profile before you run code.

## Troubleshooting

- **Create, Rename, or Delete is unavailable.** Ask your project administrator to check your profile permissions.
- **The profile no longer exists.** Refresh the list and choose a current profile. In the Workbench, **Run without a profile** starts an unprofiled session instead.
- **The list or save fails.** Use **Retry** where shown, or retry the save. Check the refreshed list before you create a duplicate.

## Next steps

[Run code in the Workbench](workbench.md) to use the selected profile.
