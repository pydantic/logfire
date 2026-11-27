# Contributing to the Logfire SDK and docs

## Contribution policy

AI makes it too easy to open issues and PRs and we get more than we can deal with. Sometimes we have to suspect that contributors have ulterior motivations such as trying to earn reputation on GitHub rather than reporting/fixing problems that they or anyone else cares about.

If we suspect that, an issue/PR may be closed as spam. We may not provide an explanation because that too would be a waste of time. Anyone is free to comment on a closed issue/PR explaining why they think it's worth reopening, whether or not they are the author.

If we suspect bad behavior or feel that you are consuming too much of our time, we will warn you that you are on the verge of being banned from the pydantic GitHub organization.

If you are reporting an issue about something outside the scope of this repo, such as a problem using the Logfire platform (which is closed source), then that's fine, and this doesn't apply.

To reduce the chances of being banned or your contributions closed:

- Please answer the following questions in the issue/PR body. Please be honest and don't overstate significance.
    - Is this something you've personally encountered in practice, or is this more of a hypothetical concern?
    - Does the problem cause a significant change in instrumented application behavior, such as an error or high resource usage?
    - Is the problem that something isn't behaving as documented?
    - Is this a security problem?
    - Is there another reason this is worth paying attention to?
    - Is the fix easy to understand and review?
    - Are you confident this is a change that we'd be happy to merge as is, or are there things that require discussion and judgment?
    - How does this change affect performance?
- If possible, please provide:
    - a complete *minimal* runnable script. If appropriate, it should send telemetry to Logfire.
    - a link to a public trace demonstrating the problem.
    - a screenshot of the Logfire UI demonstrating the problem.

## How to contribute

1. Fork and clone the repository
2. [Install uv](https://docs.astral.sh/uv/getting-started/installation/)
3. [Install pre-commit](https://pre-commit.com/#install)
4. Run `make install` to install dependencies
5. Run `make test` to run unit tests
6. Run `make test-update-examples` to format and update examples in the docs
7. Run `make format` to format code
8. Run `make lint` to lint code
9. Preview documentation through the unified site:
   - Pydantic organization members can run `make docs-serve`
   - External contributors can ask a maintainer to add the `trigger:docs` label to their pull request

You're now set up to start contributing!

Local preview requires Node.js 24, pnpm, uv, and access to the private `pydantic/unified-docs`
repository. Put its checkout beside this repository or set
`UNIFIED_DOCS_PATH=/path/to/unified-docs`. Set `DOCS_PORT=4322` to use a different local port.
