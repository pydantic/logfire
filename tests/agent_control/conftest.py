"""Fixtures for the Agent Control tests: a local Logfire project, and no leaked process state."""

from __future__ import annotations

import json
import pathlib
from collections.abc import Iterator
from typing import Any, cast

import pytest
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from pydantic import __version__ as pydantic_version

import logfire
from logfire._internal.utils import get_version
from logfire.agent_control._control import reset_baseline_publish_guard
from logfire.agent_control._reporting import reset_warned_messages
from logfire.testing import CaptureLogfire
from logfire.variables import LabeledValue, Rollout, VariableConfig, VariablesConfig
from logfire.variables.local import LocalVariableProvider

if get_version(pydantic_version) < get_version('2.12.0'):  # pragma: no cover
    # `google-adk` requires pydantic 2.12, so the `deps_test` sweep's older-pydantic legs install a
    # combination its metadata rules out. Skipping the directory (rather than each module) also skips
    # its conftest, which imports ADK at module level.
    collect_ignore = ['google_adk']


@pytest.fixture(autouse=True)
def _reset_process_state() -> Iterator[None]:  # pyright: ignore[reportUnusedFunction]
    """Forget what this process has already warned about and already published.

    Both guards exist so a long-running agent says a thing once; both would otherwise make a test's
    outcome depend on which tests ran before it.
    """
    reset_warned_messages()
    reset_baseline_publish_guard()
    yield
    reset_warned_messages()
    reset_baseline_publish_guard()


@pytest.fixture
def project(capfire: CaptureLogfire) -> Iterator[LocalVariableProvider]:
    """An empty Logfire project backed by a local variables provider, for the rest of the test.

    Returned as the provider itself so a test can assert what was written to the project, which is
    half of what publishing a baseline is for. The baseline configuration is restored on the way out
    so a reconfigured provider does not leak into the next test.
    """
    logfire.configure(
        send_to_logfire=False,
        console=False,
        variables=logfire.LocalVariablesOptions(config=VariablesConfig(variables={})),
        additional_span_processors=[SimpleSpanProcessor(capfire.exporter)],
    )
    try:
        yield cast(LocalVariableProvider, logfire.DEFAULT_LOGFIRE_INSTANCE.config.get_variable_provider())
    finally:
        logfire.configure(send_to_logfire=False, console=False)


def publish(provider: LocalVariableProvider, name: str, value: Any, *, label: str = 'production') -> VariableConfig:
    """Put `value` in the project under one label, the shape a project has once someone saved in the UI."""
    return provider.create_variable(
        VariableConfig(
            name=name,
            labels={label: LabeledValue(version=1, serialized_value=json.dumps(value))},
            rollout=Rollout(labels={label: 1.0}),
            overrides=[],
        )
    )


SPEC = pathlib.Path(__file__).parent / 'spec'
"""The cross-language vectors both cores are tested against; see `spec/README.md` beside them."""


def _vectors(name: str) -> list[dict[str, Any]]:
    return cast('list[dict[str, Any]]', json.loads((SPEC / name).read_text()))


def expand_repeats(value: Any) -> Any:
    """Expand the vector files' `{repeat, times}` shorthand, which keeps the 64 KiB cases readable."""
    if isinstance(value, dict):
        typed = cast(dict[str, Any], value)
        if set(typed) == {'repeat', 'times'}:
            return cast(str, typed['repeat']) * cast(int, typed['times'])
        return {key: expand_repeats(item) for key, item in typed.items()}
    if isinstance(value, list):
        return [expand_repeats(item) for item in cast(list[Any], value)]
    return value


@pytest.fixture(scope='session')
def agent_name_vectors() -> list[dict[str, Any]]:
    return _vectors('agent-name.json')


@pytest.fixture(scope='session')
def baseline_vectors() -> list[dict[str, Any]]:
    return _vectors('baseline.json')


@pytest.fixture(scope='session')
def config_parsing_vectors() -> list[dict[str, Any]]:
    return _vectors('config-parsing.json')
