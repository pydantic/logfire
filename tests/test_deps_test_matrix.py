"""Keep the dependency workflow complete as supported minor versions advance."""

import sys
from pathlib import Path

import yaml
from packaging.requirements import Requirement
from packaging.version import Version

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib


def test_deps_test_matrix_covers_every_supported_minor_once() -> None:
    root = Path(__file__).parents[1]
    workflow = yaml.safe_load((root / '.github/workflows/deps_test.yml').read_text())
    matrix = workflow['jobs']['test']['strategy']['matrix']
    # A base Python axis would multiply these dependency cases unnecessarily.
    assert set(matrix) == {'include'}
    cases: list[dict[str, str]] = matrix['include']
    pairs = [(case['pydantic-version'], case['otel-version']) for case in cases]
    assert len(pairs) == len(set(pairs)), 'Duplicate dependency combinations in the matrix'

    lock = tomllib.loads((root / 'uv.lock').read_text())
    latest_pydantic = max(Version(package['version']) for package in lock['package'] if package['name'] == 'pydantic')
    latest_otel = max(
        Version(package['version']) for package in lock['package'] if package['name'] == 'opentelemetry-sdk'
    )
    assert latest_pydantic.major == 2 and not latest_pydantic.is_prerelease
    assert latest_otel.major == 1 and not latest_otel.is_prerelease

    sdk = tomllib.loads((root / 'logfire-sdk/pyproject.toml').read_text())
    requirements = [Requirement(dependency) for dependency in sdk['project']['dependencies']]
    otel_requirement = next(requirement for requirement in requirements if requirement.name == 'opentelemetry-sdk')
    assert latest_otel in otel_requirement.specifier
    first_otel = max(Version(bound.version) for bound in otel_requirement.specifier if bound.operator in {'>=', '>'})
    assert first_otel.major == 1

    # Pydantic 2.4 is the existing compatibility floor; OTel's floor follows SDK metadata.
    pydantic_minors = {f'2.{minor}' for minor in range(4, latest_pydantic.minor + 1)}
    otel_minors = {f'1.{minor}' for minor in range(first_otel.minor, latest_otel.minor + 1)}
    latest_pydantic_minor = f'2.{latest_pydantic.minor}'
    latest_otel_minor = f'1.{latest_otel.minor}'
    expected_pairs = {(minor, latest_otel_minor) for minor in pydantic_minors} | {
        (latest_pydantic_minor, minor) for minor in otel_minors
    }
    assert set(pairs) == expected_pairs
