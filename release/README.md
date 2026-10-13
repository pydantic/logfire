# Release Instructions

This applies to maintainers preparing a new release.

## Semi-automated release process

### Prerequisites:

* The `gh` cli is installed and ready for use:
    * See installation instructions [here](https://github.com/cli/cli#installation)
    * See the quickstart instructions [here](https://docs.github.com/en/github-cli/github-cli/quickstart)
        * Run `gh auth` to authenticate with GitHub, which is needed for the API calls made in the release process.
* Your development environment is setup (you've run `make install`) and you have the necessary dev dependencies (like `requests`) installed.

1. Run `uv run release/prepare.py {VERSION}` from the root of the repository. This will:
    * Update the version number in the `pyproject.toml` files in the root and in `logfire-api`.
    * Add a new section to CHANGELOG.md with a title containing the version number tag and current date.
    * Add a line at the end of this section that looks something like [v1.0.1]: https://github.com/pydantic/logfire/compare/v{PREV_VERSION}...v1.0.1 but with the correct version number tags.
2. Curate the changes in CHANGELOG.md:
    * Make sure the markdown is valid; in particular, check text that should be in code-blocks is.
    * Mark any breaking changes with **Breaking Change:**.
    * Deduplicate the packaging entries to include only the most recent version bumps for each package.
3. Run `uv run release/push.py` from the root of the repository. This will:
    * Create a PR with the changes you made in the previous steps.
    * Add a label to the PR to indicate that it's a release PR.
    * Open a draft release on GitHub with the changes you made in the previous steps.
4. Review the PR and merge it.
5. Publish the release and wait for the CI to finish building and publishing the new version.

## Manual release process

If you're doing a release from a branch other than `main`, we'd recommend just going through the release process manually.

1. Update generated stubs just in case it should have been done in a previous PR via `make generate-stubs`.
2. Create a GitHub release draft with a new version number tag, generate release notes, and edit them to exclude irrelevant things like docs updates.
3. Add a new section to CHANGELOG.md with a title containing the version number tag and current date, and copy in the release notes.
4. Add a line to the end of the file that looks something like [v1.0.1]: https://github.com/pydantic/logfire/compare/v1.0.0...v1.0.1 but with the correct version number tags.
5. Update the version number in the two `pyproject.toml` files in the root and in `logfire-api`.
6. Push and merge a PR with these changes.
7. Publish the GitHub release draft and wait for the CI to finish building and publishing the new version.
