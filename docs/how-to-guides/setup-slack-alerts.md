# Setup Slack Alerting

*Logfire** allows you to send alerts via **Slack** based upon the configured alert criteria.

## Creating a Slack Incoming Webhook

**Logfire** uses **Slack's** Incoming Webhooks feature to send alerts.

The [Incoming Webhooks Slack docs](https://api.slack.com/messaging/webhooks) has all the details on setting up and using incoming webhooks.

For brevity, here's a list of steps you will need to perform:

1. In your Slack Workspace, create or identify a channel where you want to send Logfire alerts.
2. Create a new Slack app (or use an existing one) by navigating to [https://api.slack.com/apps/new](https://api.slack.com/apps/new).  Give this a meaningful name such as "Logfire Alerts" or similar so you can identify it later.
3. In the [Apps Management Dashboard](https://api.slack.com/apps), Underneath the **Features** heading on the side bar, select **Incoming Webhooks**
4. Click on the **Add New Webhook** button.  This will guide you to a page where you select the channel you want to send alerts to.
5. Click the **Allow** button.  You will be redirected back to the **Incoming Webhooks** page, and in the list, you will see your new Webhook URL.  This will be a URL that looks similar to something like this:
  ```
  https://hooks.slack.com/services/...
  ```
6. Copy that somewhere, and save it for the next step


## Creating an Alert

There are a few ways to create an alert.  You can:

* Follow our [Detect Service is Down](./detect-service-is-down.md) guide
* Have a look at the [alerts documentation](../guides/web-ui/alerts.md).

### Define alert

We'll create an alert that will let us know if any HTTP request takes longer than a second to execute.

* Login to **Logfire** and [navigate to your project](https://logfire-us.pydantic.dev/-/redirect/latest-project)
* Click on **Alerts** in the top navigation bar
* Select the **New Alert** button in the top right
* Let's give this Alert a name of **Slow Requests**
* For the query, we'll group results by the http path and duration.  We want to include the **max** duration in a given time frame.  We also want to filter out any traces that aren't http requests, and order by the max duration, so we can see which routes are the slowest.  This query looks like:
  ```sql
  SELECT
      max(duration),
      attributes->>'http.route'
  FROM
      records
  WHERE
      duration > 1
      AND attributes->>'http.route' IS NOT NULL
  GROUP BY
      attributes->>'http.route'
  ORDER BY
    max(duration) desc
  ```
* Click **Preview query results** and make sure you get some results back.  If your service is lightning fast, firstly congratulations! Secondly try adjust the duration cutoff to something smaller, like `duration > 0.1` (i.e, any requests taking longer than 100ms).

    ![](../../images/guide/browser-alerts-create-alert.png)

* You can adjust when alerts are sent based upon the alert parameters.  With this style of alert, we just want to know if anything within the last 5 minutes has been slow.  So we can use the following options:
    * **Execute the query**: every 5 minutes
    * **Include rows from**: the last 5 minutes
    * **Notify me when**: the query has any results

    ![](../../images/guide/browser-alerts-parameters.png)

### Send Alert to a Slack Channel

Our alert is almost done, let's send it to a slack channel.

For this, you will need the [Webhook URL](#creating-a-slack-incoming-webhook) you created & copied from the  Slack [Apps Management Dashboard](https://api.slack.com/apps).

Let's set up a channel, then test that alerts can be sent with the URL:

* Select **New channel** to open the New Channel dialog
* Put in a name such as **Logfire Alerts**.  This does need to be the name of your Slack     channel
* Select **Slack** as the format
* Paste in your Webhook URL from the Slack [Apps Management Dashboard]    (https://api.slack.com/apps)
* Click on **Send a test alert** and check that you can see the alert in Slack.
* Click **Create Channel** to create the channel and close the dialog
* Click the checkbox next to your new channel to select it

    ![](../../images/guide/browser-alerts-create-channel.png)

Once all done, select **Create alert** to save all your changes.

You will now receive notifications within your slack channel when the alert is triggered!
