Goal: create a PR in which all dependencies are updated to their latest versions and CI is passing.

Steps:

Stop and complain if there are uncommitted changes in the working directory.
git checkout main && git pull origin main
git checkout -b update-deps-<date>
uv sync --upgrade
git commit -am "chore: Update dependencies"

Run these, make any fixes needed, and commit the results (including automated changes) for each step where there are changes:

make format && make lint && make typecheck && uv run mkdocs build --no-strict
(usually these all pass without changes)

uv run pytest --inline-snapshot=fix

Running tests the first time will likely update some snapshots. Just commit those changes even if some tests are still failing.

Run failed tests again. If the same snapshots get updated again, use `dirty_equals` matchers to handle non-deterministic fields.

For remaining test failures, investigate and explain the problem.

If everything is passing, push the branch and display the link to create a PR.
