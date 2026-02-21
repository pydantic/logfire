# Managing Variables in the Logfire UI

The Logfire web UI provides a complete interface for managing your variables without any code changes. You can find it under **Settings > Variables** in your project. The page includes two tabs:

- **Variables**: browse, create, and manage your managed variables
- **Types**: define reusable JSON schemas for custom variable types

Clicking a variable opens its **detail page**, which has four tabs: **Values**, **Targeting**, **History**, and **Settings**.

![Variables list](../images/variables-list.png)

## Creating a Variable

To create a new variable, click **New variable** to open the create page and fill in:

- **Name**: A valid Python identifier (e.g., `agent_config`, `feature_flag`)
- **Description**: Optional text explaining what the variable controls
- **Type**: Choose from:
    - **Text**: Plain text values, ideal for prompts and messages
    - **Number**: Numeric values for thresholds, limits, etc.
    - **Boolean**: True/false flags for feature toggles
    - **JSON**: Complex structured data matching your Pydantic models
    - **Custom Types**: Reusable schemas created under the **Types** tab

For **JSON** variables, you can optionally provide a **JSON Schema** to validate version values in the UI.
For **Custom Types**, the schema is derived from the type and shown read-only; edit the type in the **Types** tab.

![Create variable form](../images/variable-create-form.png)

## Working with Values and Labels

The **Values tab** is the primary interface for viewing and editing your variable's content. It combines label management with value editing in a single view.

The left sidebar shows all labels (both active and inactive), while the right panel displays the value for the selected label. Each label in the sidebar shows its name and what it points to (e.g., a version number, another label, or "latest").

- Select a label in the sidebar to view its current value
- Click the **copy** button to copy the displayed value to your clipboard
- Click the **compare** button to diff the selected label's value against another label — useful for reviewing differences between production and staging prompts, for example
- Click **Edit** to modify the value, then **Save new version** to create a new version and assign it to the selected label
- Click **Add label** to create new labels pointing to a specific version, another label, the latest version, or the code default

![Variable detail values](../images/variable-detail-values.png)

**Labels** are mutable pointers to specific versions. They work like Docker tags or git branch names — you can move them to point at any version at any time.

Common label patterns:

- **`production`** / **`staging`** / **`canary`**: Environment-based labels for gradual rollouts
- **`control`** / **`treatment`**: A/B testing labels
- **`stable`** / **`experimental`**: Risk-based labels

!!! note "No labels = code default"
    If a variable has no labels configured in its rollout, your application serves the code default (the `default` value passed to `logfire.var()`). To serve the latest version instead, create a label that references `latest` and include it in your rollout.

## Browsing Version History

Each variable has a **linear version history** — an append-only sequence of immutable value snapshots. Versions are numbered sequentially (1, 2, 3, ...) and once created, a version's value never changes.

The **History tab** lets you browse all saved versions:

- Each version card shows its number, creation time, author, assigned labels, and description
- Expand a version to see its full value
- Use the action buttons on each version to **edit from that version** (loads its value into the Values tab), **assign a label**, **copy the value**, **compare** against another version, or **delete** the version
- Filter versions by label using the dropdown at the top

![Variable detail history](../images/variable-detail-history.png)

!!! tip "Using the example value"
    When you push a variable from code using `logfire.variables_push()`, the code's default value is stored as an "example". This example appears pre-filled when you create a new version in the UI, making it easy to start from a working configuration and modify it.

## Configuring Label Routing

The **Targeting tab > Default** section controls what percentage of requests receive each labeled version. The weights are entered as percentages (0–100%) and must sum to 100% or less:

- Set `production` to `90` and `canary` to `10` for a 10% canary deployment
- Set `control` to `50` and `treatment` to `50` for a 50/50 A/B test
- To send some traffic to the latest version, create a label that references `latest` and include it in the rollout — for example, a `latest` label referencing latest at `10` and `control` at `50` sends 10% of traffic to the latest version, 50% to the control label, and the remaining 40% falls back to the code default
- If weights sum to less than 100%, the remaining percentage uses the **code default**
- If no labels are in the rollout (empty), all traffic uses the code default

## Targeting with Conditional Rules

The **Targeting tab > Conditional Rules** section lets you route specific users or segments to specific labels based on attributes. Rules are evaluated in order, and the first matching rule determines the rollout.

To add a targeting rule:

1. Click **Add Rule** in the Conditional Rules section
2. Give the rule a name and optional description
3. Add one or more conditions (all conditions must match):
    - Choose an attribute name (e.g., `plan`, `region`, `is_beta_user`)
    - Select an operator (`equals`, `does not equal`, `is in`, `is not in`, `matches regex`, etc.)
    - Enter the value to match and its type (`str`, `int`, `float`, `bool`)
4. Configure the rollout percentages (by label) when this rule matches

For example, to give enterprise customers the production experience:

- Condition: `plan` equals `enterprise`
- Rollout: `production` = 100%

![Variable detail targeting](../images/variable-detail-routing.png)

!!! important "Variable names must match"
    The variable name in the UI must exactly match the `name` parameter in your `logfire.var()` call. If they don't match, your application will use the code default instead of the remote configuration.
