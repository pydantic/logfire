---
name: update-deps
description: "Update all project dependencies to their latest versions, fix compatibility failures, and open a passing PR. Use only when the user explicitly asks to run a dependency update."
---

# Update dependencies

## Prepare the branch

1. Stop and report any uncommitted changes. Do not modify or stash them.
2. Run `git checkout main && git pull origin main`.
3. Create `update-deps-<date>`.
4. Run `uv sync --upgrade`.
5. Commit only `uv.lock` with `gcap uv.lock -m "chore: Update dependencies"`.

Always list specific files in every staging and commit command. Never use blanket staging or `git commit -am`.

## Validate locally

Run `make format && make lint && make typecheck && make docs`. Commit any automated changes as focused commits.

Run `uv run pytest --inline-snapshot=fix`. The first run may update snapshots. Inspect and commit valid snapshot changes even if other tests failed, then rerun only the failed tests. If snapshots change repeatedly, replace nondeterministic fields with appropriate `dirty_equals` matchers.

Do not rerun the full suite locally after the first run; CI will do that.

## Open and finish the PR

Push the branch and open a non-draft PR with no description and the `test:all-deps` label. Open it even if failures remain so CI can expose version-specific compatibility failures.

Keep the label on the PR. It runs every supported Pydantic and OpenTelemetry version when added and after each later push. Do not treat regular CI passing as sufficient.

Watch both regular CI and the full dependency compatibility workflow. Investigate failures across the whole affected dependency-version range, make small focused commits, and continue until all checks pass and no review threads need a response.
