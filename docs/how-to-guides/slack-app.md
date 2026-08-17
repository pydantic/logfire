---
title: Send Logfire Alerts to Slack with the Slack App
description: "Connect a Slack workspace to Logfire once, then send alerts and issues to any channel by picking it from a list. No webhook URL to create, copy, or store."
---

# Slack App

!!! info "Beta"
    The Slack App is available to every organization and is marked **Beta** in the app. It works for alerts, issues, and saved searches today.

Connect a Slack workspace to your Logfire organization once, then point any notification channel at a Slack channel by picking it from a list.

This is the recommended way to get Logfire notifications into Slack. The [webhook route](setup-slack-alerts.md) still works and is the right choice when you cannot install an app into the workspace.

## Why use the app instead of a webhook

| | Slack App | Slack webhook |
| --- | --- | --- |
| Setup | Approve the app once per workspace | Create a Slack app and a webhook per channel |
| Secret to manage | None. Logfire stores the workspace grant | A webhook URL, which is a bearer secret |
| Choosing a channel | Pick from a list of channels the bot is in | Fixed at webhook creation; a new channel means a new URL |
| Adding a second channel | Pick another channel | Create another webhook |
| Revoking access | Disconnect in Logfire, or uninstall in Slack | Find and delete the right webhook |

## Before you start

You need:

- **In Logfire**: permission to change organization settings. The **Connections** page is visible to members who can write to the organization, typically an owner or admin.
- **In Slack**: the ability to install an app into your workspace. Many workspaces restrict this to admins, or route it through an approval request.
- **A channel** to post into, and the ability to invite an app to it.

Connections are organization-level: one workspace install serves every project in the organization.

## 1. Connect the workspace

1. Open your organization's **Settings**, then **Connections** under **Developer**.
2. Find the **Slack** row and click **Connect**.
3. Slack asks which workspace to install into and lists the permissions the app requests. Approve it.

You land back on **Connections**, where the Slack row now names the connected workspace.

!!! note "Self-hosted deployments"
    Slack requires credentials the operator configures for the deployment, so **Connections** is off by default when you host Logfire yourself. If you do not see it, ask whoever runs your instance to enable it.

## 2. Invite the app to the channel

In Slack, run this in the channel you want notifications in:

```
/invite @Logfire
```

Logfire only lists channels the app is a member of, so this step is what makes a channel selectable. It also means a channel you can pick is a channel Logfire can post to.

## 3. Create the channel in Logfire

A *notification channel* in Logfire is a destination you attach to alerts and issues.

1. In your project, go to **Delivery** → **Channels** in the **Notify** section of the sidebar, then click **New channel**. You can also create one inline from the **Send notifications to** section of an alert form.
2. Name it. This is a Logfire label, not the Slack channel name.
3. Pick **Slack App** as the type. (**Slack Webhook** is the other route, covered in [Setup Slack Alerts](setup-slack-alerts.md).)
4. Pick the **Slack workspace** you connected.
5. Pick the **Slack channel**. Only channels the app was invited to appear here.
6. Click **Send test message**. A sample notification posts to the channel.

The test must succeed before the channel can be created. That is deliberate: a Slack destination that silently drops messages is worse than no destination, and the moment to find out is now rather than during an incident.

## 4. Use the channel

Select the channel anywhere Logfire sends notifications:

- **Alerts**: the **Send notifications to** section of the alert form. See the [alerts guide](../guides/web-ui/alerts.md).
- **Issues** and **saved searches**: the notification settings on each.

One channel can serve many alerts, and one alert can notify several channels.

## Troubleshooting

**The channel I want is not in the list.** The app is not in it. Run `/invite @Logfire` in Slack, then reopen the list.

**Private channels are missing.** Workspaces connected before Logfire asked for private-channel access can only list public channels, and the channel picker says so. Reconnect Slack under **Settings** → **Connections** to include them.

**The workspace has more channels than the list shows.** Very large workspaces are listed up to a limit, and the picker's search covers only what it listed. Invite the app to the channel you want, then look again.

**Notifications stopped arriving.** Check the alert's run history: a failed delivery is recorded against the channel. The usual causes are the app being removed from the channel, the channel being archived, and the app being uninstalled from the workspace. Reopen the channel and use **Send test message** to confirm a fix.

**A test message fails with an invite instruction.** The app was removed from the channel after you selected it. Re-invite it and test again.

## Removing access

- **Disconnect in Logfire** (**Settings** → **Connections**) to revoke the grant. Channels using that workspace stop delivering.
- **Uninstall in Slack** to do the same from the other side. Logfire marks the install revoked and its channels stop working until you connect again.

A Slack install belongs to the workspace, so if several Logfire organizations connected the same workspace, revoking affects all of them. Reconnecting is a fresh install rather than a repair: the old grant is gone.
