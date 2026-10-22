from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

pytest.importorskip('fastapi', reason='FastAPI requires pydantic>=2.7', exc_type=ImportError)


@pytest.mark.parametrize('scenario', ['live', 'cold-start'])
def test_feature_flags_demo_over_real_http(scenario: str):
    result = subprocess.run(
        [sys.executable, str(Path(__file__).with_name('feature_flags_demo_probe.py')), scenario],
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
