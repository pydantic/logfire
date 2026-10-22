from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

pytest.importorskip('fastapi', reason='FastAPI requires pydantic>=2.7', exc_type=ImportError)


@pytest.mark.parametrize(
    ('scenario', 'wait_for_recovery_poll'), [('live', False), ('cold-start', False), ('cold-start', True)]
)
def test_feature_flags_demo_over_real_http(scenario: str, wait_for_recovery_poll: bool):
    result = subprocess.run(
        [
            sys.executable,
            str(Path(__file__).with_name('feature_flags_demo_probe.py')),
            scenario,
            *(['--wait-for-recovery-poll'] if wait_for_recovery_poll else []),
        ],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(result.stdout)
    assert report['scenario'] == scenario
    assert report['requests'] >= 100
    assert report['flag_evaluations'] >= 1_500
    assert report['cache_phase_revalidations'] <= (1 if scenario == 'cold-start' else 0)
    if wait_for_recovery_poll:
        assert report['cache_phase_revalidations'] == 1
    assert report['telemetry_private'] is True
    assert report['clean_shutdown'] is True


def test_feature_flags_demo_local_defaults():
    result = subprocess.run(
        [sys.executable, str(Path(__file__).with_name('feature_flags_demo_probe.py')), 'local'],
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout) == {'scenario': 'local', 'requests': 2, 'clean_shutdown': True}


def test_feature_flags_demo_provider_lifecycle():
    result = subprocess.run(
        [sys.executable, str(Path(__file__).with_name('feature_flags_demo_probe.py')), 'lifecycle'],
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout) == {'scenario': 'lifecycle', 'requests': 2, 'domains_preserved': True}
