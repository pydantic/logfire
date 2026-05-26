.DEFAULT_GOAL := all

.PHONY: .uv  # Check that uv is installed
.uv:
	@uv --version || echo 'Please install uv: https://docs.astral.sh/uv/getting-started/installation/'

.PHONY: .pre-commit  # Check that pre-commit is installed
.pre-commit:
	@pre-commit -V || echo 'Please install pre-commit: https://pre-commit.com/'

.PHONY: install  # Install the package, dependencies, and pre-commit for local development
install: .uv .pre-commit
	uv sync --frozen
	uv pip install -e logfire-api
	pre-commit install --install-hooks

.PHONY: format  # Format the code
format:
	uv run ruff format
	uv run ruff check --fix

.PHONY: lint  # Lint the code
lint:
	uv run ruff check
	uv run ruff format --check --diff

.PHONY: typecheck  # Typecheck the code
typecheck:
	uv run pyright

.PHONY: test  # Run the tests
test:
	uv run --no-sync pytest -n auto --dist=loadgroup

.PHONY: test-update-examples  # Update the examples in the documentation
test-update-examples:
	uv run pytest --update-examples -k test_docs

.PHONY: generate-stubs  # Generate stubs for logfire-api
generate-stubs:
	uv run stubgen -p logfire --include-docstrings --no-analysis
	rsync -a out/logfire/ logfire-api/logfire_api/
	rm -rf out
	# || true so that we ignore the test failure on the first pass, it should report as skipped on the second
	uv run pytest ./tests/test_logfire_api.py::test_override_init_pyi || true
	uv run pytest ./tests/test_logfire_api.py::test_override_init_pyi

.PHONY: testcov  # Run tests and generate a coverage report
testcov:
	uv run --no-sync coverage run -m pytest -n auto --dist=loadgroup
	uv run coverage combine
	@echo "building coverage html"
	uv run coverage html --show-contexts

.PHONY: test-pyodide  # Check logfire runs with pyodide
test-pyodide:
	uv build
	cd pyodide_test && npm install && npm test

.PHONY: docs docs-serve  # Documentation is built by pydantic/unified-docs
docs docs-serve:
	@echo "Logfire docs are built by pydantic/unified-docs; this repo no longer runs MkDocs."

.PHONY: all
all: format lint test

.PHONY: cf-pages-build  # Deprecated Cloudflare Pages docs build
cf-pages-build:
	@echo "Cloudflare Pages docs builds are disabled; docs are deployed by pydantic/unified-docs."
	@mkdir -p site
	@printf '%s\n' '<!doctype html><title>Logfire docs build disabled</title><p>Logfire docs are deployed by pydantic/unified-docs.</p>' > site/index.html
