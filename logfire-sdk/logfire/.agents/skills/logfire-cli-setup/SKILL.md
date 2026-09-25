---
name: logfire-cli-setup
description: Continue Logfire setup from a copied Rust CLI wizard handoff after it has connected the exact project. Do not use for standalone login or the older Python and JavaScript CLI workflows.
---

# Continue Logfire setup

Use this skill only with a handoff copied from the Rust Logfire CLI's wizard.
The handoff identifies the Logfire origin, organization, project, task, and
exact CLI executable. If that context is missing, ask the user to rerun the
wizard or use `wizard --print-prompt` through the same CLI for a complete
offline handoff. Do not guess a project or substitute a repository-local
`logfire` executable. If the exact executable is unavailable in your
environment, ask the user for a usable handoff instead of installing another
CLI.

The wizard has already authenticated, selected the project, and saved the local
SDK credential. Treat that target as confirmed. Do not rerun `auth`, `signup`,
`init`, `mcp context`, or `project current` merely because a public setup guide
would normally start with login. Never read or display the credential. If an
instrumented application rejects it, recover through the exact CLI and target
in the handoff; ask the user before choosing a different project.

Read the repository instructions and inspect the application. Follow the
handoff's task, or default to instrumenting one representative application
service. Route infrastructure-only work to `logfire-infrastructure`, evaluations
to `logfire-evals`, and telemetry investigation to `logfire-query`. For an
application setup task, use `logfire-instrumentation`. For tasks without a
matching bundled skill, consult the exact CLI's help and product docs instead
of pretending they are instrumentation tasks. Do not expand the task solely
because the repository contains incidental infrastructure or evaluation files.

When a bundled skill matches, load only that skill from the same CLI executable
with `skill prompt <name> --no-input --output json`; pass the handoff's target
and organization as global flags and follow `data.prompt`. Use `skill read` for
references named by that release-bound skill. The CLI's embedded instructions,
not the older public Python or JavaScript CLI examples, govern command names
and credential handling.

For instrumentation, run the application and check fresh telemetry in the exact
project. A successful process exit or browser visit alone does not prove
ingestion. For other tasks, verify the requested result. Report what you
verified, what remains unverified, and a link to the relevant project view when
available. Pause for browser authentication, unresolved app/project ambiguity,
material production cost or telemetry increases, deployment changes, and
destructive or unrelated work.
