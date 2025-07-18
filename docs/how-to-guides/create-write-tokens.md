To send data to **Logfire**, you need to create a write token.
A write token is a unique identifier that allows you to send data to a specific **Logfire** project.
If you set up Logfire according to the [getting started guide](../index.md), you already have a write token locally tied to the project you created.
But if you want to configure other computers to write to that project, for example in a deployed application, you need to create a new write token.

You can create a write token by following these steps:

1. Open the **Logfire** web interface at [logfire.pydantic.dev](https://logfire.pydantic.dev).
2. Select your project from the **Projects** section on the left hand side of the page.
3. Click on the ⚙️ **Settings** tab in the top right corner of the page.
4. Select the **Write tokens** tab from the left hand menu.
5. Click on the **New write token** button.

After creating the write token, you'll see a dialog with the token value.
**Copy this value and store it securely, it will not be shown again**.

Now you can use this write token to send data to your **Logfire** project from any computer or application.

We recommend you inject your write token via environment variables in your deployed application.
Set the token as the value for the environment variable `LOGFIRE_TOKEN` and logfire will automatically use it to send data to your project.

## Setting `send_to_logfire='if-token-present'`

You may want to not send data to logfire during local development, but still have the option to send it in production without changing your code.
To do this we provide the parameter `send_to_logfire='if-token-present'` in the `logfire.configure()` function.
If you set it to `'if-token-present'`, logfire will only send data to logfire if a write token is present in the environment variable `LOGFIRE_TOKEN` or there is a token saved locally.
If you run tests in CI no data will be sent.

You can also set the environment variable `LOGFIRE_SEND_TO_LOGFIRE` to configure this option.
For example, you can set it to `LOGFIRE_SEND_TO_LOGFIRE=true` in your deployed application and `LOGFIRE_SEND_TO_LOGFIRE=false` in your tests setup.
