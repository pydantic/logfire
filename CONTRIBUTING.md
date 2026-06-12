# Contributing to the Logfire SDK and docs

We'd love anyone interested to contribute to the Logfire SDK and documentation.

## How to contribute

1. Fork and clone the repository
2. [Install uv](https://docs.astral.sh/uv/getting-started/installation/)
3. [Install pre-commit](https://pre-commit.com/#install)
4. Run `make install` to install dependencies
5. Run `make test` to run unit tests
6. Run `make test-update-examples` to format and update examples in the docs
7. Run `make format` to format code
8. Run `make lint` to lint code
9. Docs are rendered by the `pydantic/unified-docs` pipeline; there is no local MkDocs build in this repository

You're now set up to start contributing!
