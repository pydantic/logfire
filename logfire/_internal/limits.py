from __future__ import annotations


def filter_package_versions(package_versions: dict[str, str]) -> dict[str, str]:
    """Filter out package versions that don't correspond to opentelemetry or logfire."""
    return {k: v for k, v in package_versions.items() if k == 'logfire' or k.startswith('opentelemetry')}
