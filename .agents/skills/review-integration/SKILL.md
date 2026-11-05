---
name: review-integration
description: "Review a PR which adds an integration/instrumentation."
---

Read dev-docs/integration-guidelines.md in the root of the repo.
Systematically ensure that every item on the list is checked.
Create a new PR stacked on top of the PR under review to fix any missing items.
Fix anything that is obviously wrong, such as failing tests.
If CI doesn't run in the PR because it's in a fork, run the full test suite locally, ensure 100% coverage as CI would, and ensure linting, formatting, and type checking pass. Commit any fixes to the new PR.
Do this in a separate worktree.
Add an inline comment to a file in the new PR for each remaining issue not addressed that needs maintainer input, whether it relates to the checklist or just anything else you notice. The comment should start with "(AI) ".
Merge main into the new PR and resolve any conflicts.
