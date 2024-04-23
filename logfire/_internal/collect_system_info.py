from __future__ import annotations

import importlib.metadata as metadata
from functools import lru_cache


@lru_cache
def collect_package_info() -> dict[str, str]:
    """Retrieve the package information for all installed packages.

    Returns:
        A dicts with the package name and version.
    """
    distributions = metadata.distributions()
    distributions = sorted(distributions, key=lambda dist: (dist.name, dist.version))
    return {dist.name: dist.version for dist in distributions}
