.DEFAULT_GOAL := all
sources = logfire tests

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
	uv run pyright $(sources)

.PHONY: test  # Run the tests
test:
	uv run coverage run -m pytest

.PHONY: generate-stubs  # Generate stubs for logfire-api
generate-stubs:
	stubgen -p logfire --include-docstrings --no-analysis
	rsync -a out/logfire/ logfire-api/logfire_api/

.PHONY: testcov  # Run tests and generate a coverage report
testcov: test
	@echo "building coverage html"
	@uv run coverage html --show-contexts

.PHONY: docs  # Build the documentation
docs:
	mkdocs build

# no strict so you can build the docs without insiders packages
.PHONY: docs-serve  # Build and serve the documentation
docs-serve:
	mkdocs serve --no-strict

.PHONY: all
all: format lint test

.PHONY: cf-pages-build  # Build the docs for GitHub Pages
cf-pages-build:
	python3 -V
	python3 -m pip install uv
	python3 -m uv pip install --system -r requirements.lock -r requirements-dev.lock
	python3 -m uv pip install --system --extra-index-url $(PPPR_URL) -U mkdocs-material mkdocstrings-python griffe==0.48.0
	python3 -m mkdocs build
