---
title: "Logfire Account Conversion: Personal to Org"
description: Convert your Logfire Personal account to an Organization account. Benefit from dedicated teams and clearly defined user and access roles.
---
# How to Convert a Personal Account to an Organization

Logfire allows you to convert your personal account into an organization, making it easier to collaborate with a team and manage projects at scale.
Converting to an organization requires selecting a [paid plan](https://pydantic.dev/pricing). You will have _5 days_ to chose a plan once you
converted your account, before the organization gets locked.

---

## 1. Open Plan & Usage Page

Navigate to your account home page, and go under the _Plan & Usage_ page.

![Plan and usage page upgrade plan](../images/guide/convert-to-org-usage-page.png)

---

## 2. Start the Conversion

Click **Upgrade plan**. A modal will appear, asking you to either convert your account or create a new organization. Choose the first option.

A new modal will appear, outlining the main points of the conversion:

- All existing **projects, members, alerts, dashboards, and settings** will be moved to the new organization.
- **Write tokens** will continue to work; you do not need to change any ingest URLs.
- You'll define your new organization's **handle** and **display name**.
- You can optionally edit the username and display name for your new personal account.

![Convert to org modal with main points](../images/guide/convert-to-org-modal-main-points.png)

Click **Acknowledge & continue** to proceed.

---

## 3. Set Up Your Organization

In the next modal, you can:

- Upload an **organization avatar**.
- Specify the **organization handle** (used in URLs).
- Set the **organization display name**.

On the right, you'll see a summary of the migration:

- All your projects and members will be moved to the new organization.
- The project URLs will change from:
  `https://logfire-eu.pydantic.dev/your-username/project-name`
  to
  `https://logfire-eu.pydantic.dev/your-org-handle/project-name`.

![Set up new organization modal](../images/guide/convert-to-org-setup-org.png)

---

## 4. Confirm New Personal Account

After setting up the organization, you'll be prompted to create a new (empty) personal account with the same name as before. You can confirm and complete the conversion, or go back if you wish to make changes.

![Confirm new personal account modal](../images/guide/convert-to-org-new-personal.png)

---

## 5. Complete the Conversion

Click **Confirm & convert**. The conversion process will complete, and you'll be redirected to the *Manage plans* page, to select a paid plan.

![Manage plans page](../images/guide/convert-to-org-manage-plans.png)

You can still make use of your new organization, but you will have _5 days_ to select a paid plan before the organization gets disabled.

---

## Summary

- All your data, projects, and settings are preserved during the migration.
- Only the URL changes to reflect the new organization handle.
- The new organization needs to be under a paid plan.
- Your new personal account will be empty, ready for individual use if needed.

---

**See also:** [Organization Structure Reference](../guides/web-ui/organizations-and-projects.md)
