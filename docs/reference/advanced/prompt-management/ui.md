---
title: "Prompt Management UI Guide"
description: "How to author, test, version, and inspect prompts in the Logfire UI."
---

# Prompt Management UI guide

The Prompt Management UI is the prompt-authoring surface. Use it to write prompt
templates, test them with saved scenarios, inspect rendered messages, and save
versions. Promotion, targeting, and rollout still happen on the prompt's backing
managed variable.

## Prompts list

Open **Prompt Management** from your project navigation. The list shows the
prompts in the project, with their display names and slugs. Create one prompt per
runtime prompt your application fetches, such as `support-agent`,
`incident-triage`, or `welcome-email`.

Each prompt has a backing managed variable named
`prompt__<slug_with_underscores>`. For example, a prompt with slug
`support-agent` is fetched from application code as `prompt__support_agent`.

## Prompt detail page

The prompt detail page has three jobs:

- author the current draft template,
- test the draft or a saved version against scenarios,
- inspect the run output before saving or promoting a version.

### Template editor

The template editor is where you write the prompt text. It supports two kinds of
placeholders:

| Syntax | Purpose |
|---|---|
| `{{customer_name}}` | Runtime template input rendered from scenario variables or application data |
| `@{support_safety_rules}@` | Managed-variable composition reference expanded from Logfire configuration |
| `@{prompt__support_style}@` | Prompt composition reference expanded through another prompt's backing variable |

The editor detects template parameters and composition references. Use those
detected chips to check that names match what your scenarios or managed variables
provide.

### Insert reference

Use **Insert reference** to add a managed-variable or prompt reference without
typing the `@{...}@` syntax by hand. Regular managed variables are inserted by
their variable name. Prompts are inserted through their backing managed-variable
name, such as `@{prompt__support_style}@`.

If you type a prompt slug without the backing prefix, Logfire can suggest the
correct `prompt__...` name when preview or run validation fails.

### Template parameters

Template parameters are the `{{...}}` values that must be available at render
time. In the editor, those values usually come from the active scenario's
variables. In production, your application supplies the same values to
`logfire.template_prompt().get(inputs)` or to its own renderer before passing the
prompt to the model.

Use plain names for simple values:

```text
customer_name = Maya Chen
```

Use dotted names for nested values:

```text
customer.name = Maya Chen
customer.tier = enterprise
```

Dotted values are available as `{{customer.name}}` and `{{customer.tier}}`.

## Scenarios panel

Scenarios are saved test cases for the prompt. A scenario contains messages and a
set of variables. The default scenario starts with a system message containing:

```text
@{prompt}@
```

That scenario-only alias is replaced with the rendered prompt during a run. Add
user messages, prior assistant messages, and tool messages when you need to test
a realistic conversation.

For example:

```text
system: @{prompt}@
user: Customer question: {{question}}
```

Then define `question` in the scenario variables panel.

## Preview and run output

Preview shows the rendered messages before they are sent to the model. It is the
first place to check when output looks surprising:

- `@{...}@` references should already be expanded.
- `{{...}}` placeholders should be replaced with scenario values.
- `@{prompt}@` should be replaced inside scenario messages.
- Tool-call `args` and tool-return `content` should render string fields
  recursively.

If preview reports a validation error, fix the template, scenario variables, or
managed-variable references before running the prompt against a model.

## Versions

Saving a version freezes the prompt template text. Versions do not freeze
scenario messages, model settings, tool definitions, managed-variable fragments,
or rollout rules.

Use versions as the stable points you can compare, promote, or roll back to.
Draft edits are not served by production traffic until you save a version and
move a serving label to it.

## Settings and tools

Prompt settings control the test environment used by Prompt Management. Tool
definitions, model selection, and advanced gateway settings affect prompt runs in
the UI. They do not become part of the prompt template your application fetches.

If your production application needs tools, configure those tools in application
code as well.

## Promotion

After saving a version, promote it from the backing managed variable:

1. Open the prompt's backing variable in **Managed Variables**.
2. Move a label such as `production`, `canary`, or `staging` to the prompt
   version you want to serve.
3. Configure rollout or targeting rules if you want a partial rollout.

For the full workflow, see [Promote and Roll Out Prompts](./promotion-and-rollouts.md).
