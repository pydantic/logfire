"""How `logfire.instrument_mcp()` tells mcp 1 from mcp 2.

mcp 2 removed `mcp.shared.session`. A `ModuleNotFoundError` for exactly that module means mcp 2 and
turns the call into a warning; any other import failure propagates. Both cases are simulated here
via `sys.modules` so they run against the locked mcp 1.
"""

import sys
from importlib import import_module
from importlib.metadata import version
from typing import Any

import pytest

import logfire
from logfire._internal.utils import get_version

# The installed MCP 1 release requires Pydantic 2.11; check before importing its models.
pytest.importorskip('pydantic', minversion='2.11')
if get_version(version('mcp')) >= get_version('2'):
    pytest.skip('Requires MCP 1', allow_module_level=True)

# On supported dependency combinations, unexpected import failures must fail collection.
import_module('logfire._internal.integrations.mcp')


def test_missing_shared_session_means_mcp_2(monkeypatch: pytest.MonkeyPatch):
    # `None` in `sys.modules` makes the import raise `ModuleNotFoundError` with `name='mcp.shared.session'`.
    monkeypatch.setitem(sys.modules, 'mcp.shared.session', None)
    with pytest.warns(UserWarning, match=r'`logfire\.instrument_mcp\(\)` is unnecessary with mcp 2') as records:
        logfire.instrument_mcp()
    assert len(records) == 1


def test_other_import_failures_propagate(monkeypatch: pytest.MonkeyPatch):
    class BrokenDependencyFinder:
        """Fails the import of `mcp.shared.session` the way a missing dependency of it would."""

        def find_spec(self, name: str, path: Any = None, target: Any = None) -> None:
            if name == 'mcp.shared.session':
                raise ModuleNotFoundError("No module named 'some_dependency'", name='some_dependency')

    monkeypatch.delitem(sys.modules, 'mcp.shared.session')
    monkeypatch.setattr(sys, 'meta_path', [BrokenDependencyFinder(), *sys.meta_path])
    with pytest.raises(ModuleNotFoundError, match='some_dependency'):
        logfire.instrument_mcp()
