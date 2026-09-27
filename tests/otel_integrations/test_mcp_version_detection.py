"""How `logfire.instrument_mcp()` tells mcp 1 from mcp 2.

mcp 2 removed `mcp.shared.session`. A `ModuleNotFoundError` for exactly that module means mcp 2 and
turns the call into a warning; any other import failure propagates. Both cases are simulated here
via `sys.modules` so they run against the locked mcp 1.
"""

import sys
from typing import Any

import pytest

import logfire

pytest.importorskip('mcp.shared.session')
# On old pydantic (e.g. the 2.4 CI job) mcp 1 itself fails to import, so the integration can't be exercised.
pytest.importorskip('logfire._internal.integrations.mcp')


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
