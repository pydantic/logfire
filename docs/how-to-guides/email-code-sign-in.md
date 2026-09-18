---
title: Sign in with an email code
description: Create or access a Logfire account with a short-lived code sent to your email address.
---

# Sign in with an email code

Use a short-lived email code to create or access your Logfire account without remembering another password.

!!! info "Beta"
    Email code sign-in is available throughout Logfire Cloud and is in Beta. You can choose password-backed signup instead.

## Create an account without a password

1. Open the Logfire sign-up page and enter your email address.
2. Select **Email me a code**.
3. Copy the six-digit code from the **Your Logfire verification code** email. The code expires after 10 minutes and works once.
4. Enter the code in Logfire, then finish creating your organization and first project.
5. Choose whether to set up an authenticator app now or later.

You can switch to **Use a password instead** before entering the code. Logfire keeps the email address you already entered.

## Sign in to an existing account

On the email sign-in page, enter your address and select **Email me a code**. Enter the six-digit code from your email.

If your account has two-factor authentication, Logfire also asks for the current code from your authenticator app or one unused recovery code. The email proves access to your inbox; the authenticator remains a separate factor.

You can select **Use your password** at any time. After a successful sign-in, Logfire marks that method as **Last used** in the same browser so it is easier to recognize next time.

## Turn email code sign-in off

Password-backed accounts can disable email code sign-in:

1. Sign in to Logfire.
2. Open **Settings → Profile**.
3. Turn **Email code sign-in** off.

Logfire invalidates codes that it issued before the setting changed. Password sign-in remains available. To turn email code sign-in on again, your account must have two-factor authentication and you must have signed in recently.

An account created without a password cannot turn off its only email sign-in method. To add one, open **Org settings → General → Account connections** and select **Set up email and password**. You can then disable email code sign-in from your profile.

## Verify the method

Sign out, return to the email sign-in page, and request a new code. The message should arrive with a six-digit code, and the code should work once. If you disabled email code sign-in, Logfire does not deliver a login code for that account, and password sign-in still works.

## Troubleshooting

### The email does not arrive

Check spam and confirm that you used the same data region as your account. US and EU accounts are separate. See [Choose a data region](../reference/data-regions.md).

### The code is rejected

Request a new code. Each code expires after 10 minutes and becomes invalid after one successful use or after you change the email code sign-in setting.

### Logfire asks for an authenticator code

Your account has two-factor authentication. Enter the current authenticator code or select **Use recovery code**. Email code sign-in does not bypass an authenticator that is already configured.

### No login code is delivered for an existing account

The account may use Google, GitHub, [organization single sign-on](sso-setup.md), or a password-backed account that disabled email code sign-in. Return to the main sign-in page and use the method already connected to the account.
