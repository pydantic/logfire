# Release instructions

Keep user-facing changes as bullets under `Unreleased` in `CHANGELOG.md`. Do not add a `New Contributors` section.

To publish a release:

1. Insert `## [vVERSION] (YYYY-MM-DD)` below `## Unreleased` so the existing bullets become the release notes.
2. Add `[vVERSION]: https://github.com/pydantic/logfire/compare/PREVIOUS_TAG...vVERSION` at the end of `CHANGELOG.md`.
3. Run `uv version VERSION`, `uv version --package logfire-api VERSION`, and `make generate-stubs`.
4. Open and merge a pull request titled `Release vVERSION`.
5. Create a GitHub release from `main` with the `vVERSION` tag and the changelog bullets as its description.

Publishing the GitHub release triggers `.github/workflows/publish.yml`. It builds and publishes both packages to PyPI.
