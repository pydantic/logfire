"""Fixtures for the LiveKit adapter tests.

The Logfire project, the process-state reset, and `publish` come from `tests/agent_control/conftest.py`;
what is here is the provider credentials a plugin refuses to be constructed without.
"""

from __future__ import annotations

import os

import pytest

import logfire
from logfire.variables import LabeledValue
from logfire.variables.local import LocalVariableProvider

# A plugin reads its credentials when it is constructed, and building a plugin is what a managed
# `model` does; no request is made unless a test is recording one. `setdefault` so that recording
# against the real providers picks up the real values from the environment.
os.environ.setdefault('GOOGLE_API_KEY', os.environ.get('GEMINI_API_KEY', 'foo'))
os.environ.setdefault('LIVEKIT_API_KEY', 'foo')
# Long enough that signing a LiveKit access token with it does not warn about the key length.
os.environ.setdefault('LIVEKIT_API_SECRET', 'foo-livekit-secret-long-enough-for-hmac-sha256')


@pytest.fixture(autouse=True, scope='module')
def _configure_logfire() -> None:  # pyright: ignore[reportUnusedFunction]
    """Configure Logfire so resolving a variable does not warn about it (warnings are errors here)."""
    logfire.configure(send_to_logfire=False, console=False)


def clear(provider: LocalVariableProvider, name: str, *, label: str = 'production') -> None:
    """Put an empty config in the project, the shape it has once someone removes every section."""
    config = provider.get_variable_config(name)
    assert config is not None
    config.labels[label] = LabeledValue(version=2, serialized_value='{}')
    provider.update_variable(name, config)
