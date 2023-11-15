from __future__ import annotations

import importlib.metadata as metadata
from functools import lru_cache
from typing import List

from typing_extensions import TypedDict


class Package(TypedDict):
    name: str
    version: str


Packages = List[Package]


@lru_cache
def collect_package_info() -> Packages:
    """Retrieve the package information for all installed packages.

    Returns:
        A list of dicts with the package name and version.
    """
    distributions = metadata.distributions()
    distributions = sorted(distributions, key=lambda dist: (dist.name, dist.version))
    return [{'name': dist.name, 'version': dist.version} for dist in distributions]
