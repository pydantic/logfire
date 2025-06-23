.DEFAULT_GOAL := all

.PHONY: .uv  # Check that uv is installed
.uv:
	@uv --version || echo 'Please install uv: https://docs.astral.sh/uv/getting-started/installation/'

.PHONY: .pre-commit  # Check that pre-commit is installed
.pre-commit:
	@pre-commit -V || echo 'Please install pre-commit: https://pre-commit.com/'

.PHONY: install  # Install the package, dependencies, and pre-commit for local development
install: .uv .pre-commit
	uv sync --frozen --group docs
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
	uv run --no-sync coverage run -m pytest -n auto --dist=loadgroup

.PHONY: generate-stubs  # Generate stubs for logfire-api
generate-stubs:
	uv run stubgen -p logfire --include-docstrings --no-analysis
	rsync -a out/logfire/ logfire-api/logfire_api/
	rm -rf out
	# || true so that we ignore the test failure on the first pass, it should report as skipped on the second
	uv run pytest ./tests/test_logfire_api.py::test_override_init_pyi || true
	uv run pytest ./tests/test_logfire_api.py::test_override_init_pyi

.PHONY: testcov  # Run tests and generate a coverage report
testcov: test
	@echo "building coverage html"
	uv run coverage html --show-contexts

.PHONY: test-pyodide  # Check logfire runs with pyodide
test-pyodide:
	uv build
	cd pyodide_test && npm install && npm test

.PHONY: docs  # Build the documentation
docs:
	uv run mkdocs build

# no strict so you can build the docs without insiders packages
.PHONY: docs-serve  # Build and serve the documentation
docs-serve:
	uv run mkdocs serve --no-strict

.PHONY: all
all: format lint test

.PHONY: cf-pages-build  # Build the docs for GitHub Pages
cf-pages-build:
	curl -LsSf https://astral.sh/uv/0.4.30/install.sh | sh
	${HOME}/.cargo/bin/uv python install 3.12
	${HOME}/.cargo/bin/uv sync --python 3.12 --frozen --group docs
	${HOME}/.cargo/bin/uv pip install --upgrade --extra-index-url $(PPPR_URL) mkdocs-material mkdocstrings-python griffe==0.48.0
	${HOME}/.cargo/bin/uv run --no-sync mkdocs build
