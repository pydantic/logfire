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
	uv run --no-sync pytest -n logical --dist=loadgroup

.PHONY: test-otel-collector
test-otel-collector:
	LOGFIRE_OTEL_COLLECTOR_TESTS=1 uv run --no-sync pytest -n 0 tests/otel_collector

.PHONY: test-feature-flags  # Run the deterministic feature-flag reliability suite
test-feature-flags:
	uv run --no-sync pytest tests/test_feature_flags.py tests/test_feature_flag_properties.py tests/test_variables.py tests/test_feature_flags_demo.py

.PHONY: demo-feature-flags  # Run the local-only support service with typed feature flags
demo-feature-flags:
	uv run --no-sync python -m examples.python.feature_flags_demo

.PHONY: test-feature-flags-demo  # Exercise the demo against real HTTP and SSE delivery
test-feature-flags-demo:
	uv run --no-sync pytest tests/test_feature_flags_demo.py

.PHONY: test-feature-flags-mutation  # Mutate the feature-flag decision and context boundaries
test-feature-flags-mutation:
	@test ! -e src
	@# Regenerate coverage-selected mutants: source mtimes alone do not track new tests or tooling.
	@set -e; mkdir src; trap 'test ! -L src/logfire || unlink src/logfire; rmdir src' EXIT; \
	test ! -L mutants; rm -rf -- mutants; \
	ln -s ../logfire-sdk/logfire src/logfire; \
	NO_PROXY='*' no_proxy='*' COVERAGE_RCFILE=/dev/null PYDANTIC_DISABLE_PLUGINS=__all__ uv run --no-sync mutmut run \
		'*VariableConfig*_select_rollout*' \
		'*VariableConfig*requires_targeting_key*' \
		'*VariablesConfig*resolve_serialized_value*' \
		'*experimental.feature_flags*' \
		'*_declaration_schema_without_defaults*' \
		'*_scrub_feature_flag_result*' \
		'*_override_key*' \
		'*_deserialize_resolved_value*' \
		'*_ManagedVariableFlagAdapter*override*' \
		'*_feature_flag_evaluation_details*' \
		'*_feature_flag_telemetry_attributes*' \
		'*_ManagedVariableFlagAdapter*resolution_telemetry_attributes*' \
		'*_ManagedVariableFlagAdapter*_get_provider_evaluation_state*' \
		'*_ManagedVariableFlagAdapter*_finalize_resolution_result*' \
		'*_ManagedVariableFlagAdapter*_result_for_provider_state*' \
		'*feature_context*'; \
	results="$$(uv run --no-sync mutmut results)"; \
	target_results="$$(printf '%s\n' "$$results" | grep -E 'VariableConfig.*(_select_rollout|requires_targeting_key)|VariablesConfig.*resolve_serialized_value|experimental.feature_flags|_declaration_schema_without_defaults|_scrub_feature_flag_result|_override_key|_deserialize_resolved_value|_feature_flag_(evaluation_details|telemetry_attributes)|_ManagedVariableFlagAdapter.*(override|resolution_telemetry_attributes|_get_provider_evaluation_state|_finalize_resolution_result|_result_for_provider_state)|feature_context' || true)"; \
	if [ -n "$$target_results" ]; then \
		printf '%s\n' "$$target_results"; \
		echo 'Feature-flag mutation testing left non-killed mutants'; \
		exit 1; \
	fi; \
	echo 'All targeted feature-flag mutants were killed.'

.PHONY: test-update-examples  # Update the examples in the documentation
test-update-examples:
	uv run pytest --update-examples -k test_docs

.PHONY: generate-stubs  # Generate stubs for logfire-api
generate-stubs:
	uv run stubgen -p logfire --include-docstrings --no-analysis
	rsync -a out/logfire/ logfire-api/logfire_api/
	rm -rf out
	uv run python scripts/postprocess_generated_stubs.py
	uv run pytest ./tests/test_logfire_api.py::test_postprocess_generated_stubs

.PHONY: testcov  # Run tests and generate a coverage report
testcov:
	uv run --no-sync coverage run -m pytest -n logical --dist=loadgroup
	uv run coverage combine
	@echo "building coverage html"
	uv run coverage html --show-contexts

.PHONY: test-pyodide  # Check logfire runs with pyodide
test-pyodide:
	uv build --package logfire-sdk
	cd pyodide_test && npm install && npm test

.PHONY: docs  # Documentation is built by pydantic/unified-docs
docs:
	@echo "Logfire docs are built by pydantic/unified-docs; this repo no longer runs MkDocs."

.PHONY: docs-serve  # Preview documentation with pydantic/unified-docs
docs-serve:
	uv run --no-project python scripts/docs_serve.py

.PHONY: all
all: format lint test

.PHONY: publish-firehose-template
publish-firehose-template:  # Publish to an existing public S3 bucket. Set FIREHOSE_PUBLISH_ARGS.
	python3 scripts/publish_firehose_template.py $(FIREHOSE_PUBLISH_ARGS)
