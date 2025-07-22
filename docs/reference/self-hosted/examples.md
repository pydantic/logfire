# Examples

This page provides some example configuration for different scenarios.

---

## Auth

Examples for configuring different [Dex connectors](https://dexidp.io/docs/connectors/)

### Azure

For Azure, we recommend creating an [OpenID connector](https://dexidp.io/docs/connectors/oidc/).

- Follow the steps to create the Azure App at [Azure Docs](https://learn.microsoft.com/en-us/power-pages/security/authentication/openid-settings#create-an-app-registration-in-azure)

    - Make sure to set the RedirectURI to ```<logfire_url>/auth-api/callback```
    - Make sure to copy the secret value when you create it

- To finish the configuration on your Helm values file, you will need:
    - Directory (Tenant) ID and     Application (client) ID, you can get both of these from the Azure App overview page
    - The client secret value you copied on the previous step

It should look something like this:
```yaml
    connectors:
      - type: oidc
        id: azuread
        name: Microsoft
        config:
          issuer: https://login.microsoftonline.com/<tenant_id>/v2.0
          clientID: <App client ID>
          clientSecret: <Client secret value>
          insecureSkipEmailVerified: true
```

### Github

For GitHub you can use the [GitHub connector](https://dexidp.io/docs/connectors/github/)

- Follow the steps for creating an OAuth app [in the GitHub docs](https://docs.github.com/en/apps/oauth-apps/building-oauth-apps/creating-an-oauth-app)

    ![Github OAuth App](../../images/self-hosted/dex-github-oauth-app.png)

    !!! note
        Make sure to set the callback URL to ```<logfire_url>/auth-api/callback```

    ![Github OAuth App Permissions](../../images/self-hosted/dex-github-oauth-app2.png)
    !!! note
        For personal apps, setting at least email read access is required here. For Organizations, this is not needed.

- After creating the app, on the ```General``` tab at the left, at the Client secrets section, click ```Generate a new client secret```, and copy the value.

- On your values file:
    ```yaml
        logfire-dex:
        ...
        config:
            connectors:
            - type: "github"
                id: "github"
                name: "GitHub"
                config:
                # You get clientID and clientSecret by creating a GitHub OAuth App
                # See https://docs.github.com/en/apps/oauth-apps/building-oauth-apps/creating-an-oauth-app
                clientID: client_id
                clientSecret: client_secret
    ```
