.DEFAULT_GOAL := all
sources = pydantic tests docs/plugins

.PHONY: .rye  # Check that Rye is installed
.rye:
	@rye --version || echo 'Please install Rye: https://rye-up.com/guide/installation/'

.PHONY: .pre-commit  # Check that pre-commit is installed
.pre-commit:
	@pre-commit -V || echo 'Please install pre-commit: https://pre-commit.com/'

.PHONY: install  # Install the package, dependencies, and pre-commit for local development
install: .rye .pre-commit
	rye show
	rye sync
	pre-commit install --install-hooks

.PHONY: format  # Format the code
format:
	rye format
	rye lint --fix

.PHONY: lint  # Lint the code
lint:
	rye lint
	rye format --check

.PHONY: test  # Run the tests
test:
	rye run coverage run -m pytest

.PHONY: testcov  # Run tests and generate a coverage report
testcov: test
	@echo "building coverage html"
	@rye run coverage html

.PHONY: docs  # Build the documentation
docs:
	rye run docs

.PHONY: docs-serve  # Build and serve the documentation
docs-serve:
	rye run docs-serve

.PHONY: all
all: format lint test

.PHONY: cf-pages-build  # Build the docs for GitHub Pages
cf-pages-build:
	python3 -V
	python3 -m pip install uv
	python3 -m uv pip install --system -r requirements.lock -r requirements-dev.lock
	python3 -m uv pip install --system --extra-index-url $(PPPR_URL) -U mkdocs-material mkdocstrings-python
	python3 -m mkdocs build
