---
title: Send Logfire Alerts to Slack with the Slack App
description: "Connect a Slack workspace to Logfire once, then send alerts and issues to an eligible channel by picking it from a list. No webhook URL to create, copy, or store."
---

# Slack App

!!! info "Beta"
    The Slack App is available to every organization and is marked **Beta** in the app. It delivers alerts and issue notifications today.

The Logfire Slack app brings your observability notifications into Slack. Install it into your workspace once, connect it to your Logfire organization, and then send alerts and issues to an eligible channel by picking it from a list.

## What the app does in Slack

- **Posts notifications** to the channels you choose: a firing alert or a new issue, rendered as a Slack message with a link back to Logfire.
- **Lists the channels it has been invited to**, so you pick a destination instead of pasting a URL.
- **Publishes a Home tab** describing the connection.
- **Collects feedback on the notifications that ask for it.** Those messages carry **👍 Useful** and **👎 Not useful** buttons, and 👎 opens a dialog for an optional note. Adding a 👍 / 👎 reaction to one of them does the same thing. Alert and issue notifications do not ask for feedback, so reacting to one does nothing.

The app never posts anywhere it has not been invited, and it does not join channels by itself.

!!! warning "AI-generated content can be inaccurate"
    Some notifications include content that Logfire generates with AI, such as a summary of what changed or a suggested cause. AI-generated content can be inaccurate, incomplete, or misleading. Treat it as a starting point for your investigation, and verify it against the linked traces and query results in Logfire before acting on it. Those are the notifications that ask for feedback: your 👍 / 👎 helps us improve them.

### Permissions it requests

| Permission | Why the app needs it |
| --- | --- |
| `chat:write` | Post notifications into the channels you pick |
| `channels:read`, `groups:read` | List public and private channels the app is a member of, for the channel picker |
| `reactions:read` | Receive the 👍 / 👎 you add to a notification that asks for feedback, as your rating of it |
| `team:read` | Show the workspace name and icon on the connection in Logfire |

The app does not read your message history or your direct messages.

### Data and privacy

Logfire stores the workspace grant (the bot token, encrypted at rest), the workspace's name and ID, the granted permissions, and the ID of each channel you select. Message content flows one way: Logfire posts notification text built from your telemetry, and the only inbound content it records is the feedback described above, meaning your rating and any note you write in the **Not useful** dialog.

Public channels that include the Logfire app are available to Logfire members who can configure notification channels. Private channels appear only to the Logfire user who connected the workspace, and only when Slack confirms that both this user and the app belong to the channel. Other Logfire members cannot browse or select those private channels.

See the [Pydantic privacy policy](https://pydantic.dev/legal/privacy-policy) for how we collect, manage, and store this data.

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

Logfire only lists channels the app is a member of, so this step is what makes a public channel selectable. For a private channel, you must also be the Logfire user who connected the workspace and a member of that channel in Slack. These checks mean a channel you can pick is a channel Logfire can post to without revealing private channels to other Logfire members.

## 3. Create the channel in Logfire

A *notification channel* in Logfire is a destination you attach to alerts and issues.

1. In your project, open **Project settings**, then select **Delivery** under **Notifications**. On the **Channels** tab, click **New channel**. You can also create one inline from the **Send notifications to** section of an alert form.
2. Name it. This is a Logfire label, not the Slack channel name.
3. Pick **Slack App** as the type. (**Slack Webhook** is the other route, covered in [Setup Slack Alerts](setup-slack-alerts.md).)
4. Pick the **Slack workspace** you connected.
5. Pick the **Slack channel**. Public channels appear when the app is a member. Private channels also require you to be the Logfire user who connected the workspace and a member of the channel in Slack.
6. Click **Send test message**. A sample notification posts to the channel.

The test must succeed before the channel can be created. That is deliberate: a Slack destination that silently drops messages is worse than no destination, and the moment to find out is now rather than during an incident.

## 4. Use the channel

Select the channel anywhere Logfire sends notifications:

- **Alerts**: the **Send notifications to** section of the alert form. See the [alerts guide](../guides/web-ui/alerts.md).
- **Issue notifications**: the notification settings on the [Issues](../guides/web-ui/issues.md) page, or the filter alert on a [saved search](../guides/web-ui/saved-searches.md). Both send the same issue notification, so pick whichever fits how you already scope issues.

One channel can serve many alerts, and one alert can notify several channels.

## Troubleshooting

**The channel I want is not in the list.** The app is not in it. Run `/invite @Logfire` in Slack, then reopen the list.

**Private channels are missing.** Only the Logfire user who connected the workspace can select private channels. If that is you, confirm that both you and the Logfire app belong to the channel. Workspaces connected before Logfire asked for private-channel access can only list public channels, and the channel picker says so. Reconnect Slack under **Settings** → **Connections** to include private channels.

**The workspace has more channels than the list shows.** Very large workspaces are listed up to a limit, and the picker's search covers only what it listed. Invite the app to the channel you want, then look again.

**Notifications stopped arriving.** Check the alert's run history: a failed delivery is recorded against the channel. The usual causes are the app being removed from the channel, the channel being archived, and the app being uninstalled from the workspace. Reopen the channel and use **Send test message** to confirm a fix.

**A test message fails with an invite instruction.** The app was removed from the channel after you selected it. Re-invite it and test again.

## Removing access

- **Disconnect in Logfire** (**Settings** → **Connections**) to revoke the grant. Channels using that workspace stop delivering.
- **Uninstall in Slack** to do the same from the other side. Logfire marks the install revoked and its channels stop working until you connect again.

A Slack install belongs to the workspace, so if several Logfire organizations connected the same workspace, revoking affects all of them. Reconnecting is a fresh install rather than a repair: the old grant is gone.

## If you cannot install an app

Some workspaces will not approve a third-party app, or route the request through an approval you would rather not wait for, while still letting members build an app of their own. In that case Logfire also delivers through an incoming webhook, which you create in your own Slack app and paste into a notification channel: see [Setup Slack Alerts](setup-slack-alerts.md). If your workspace allows neither, ask an admin to approve the Logfire app; there is no third route.

That route works, but it puts a bearer secret in your hands, fixes each webhook to a single channel, and gives Logfire no way to tell you whether the destination is still reachable. Prefer the app when you can install it.
