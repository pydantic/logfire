from __future__ import annotations

import importlib.metadata as metadata
from typing import List

from typing_extensions import TypedDict


class Package(TypedDict):
    name: str
    version: str


Packages = List[Package]


def collect_package_info() -> Packages:
    """Return package information for all installed packages"""
    distributions = metadata.distributions()
    distributions = sorted(distributions, key=lambda dist: (dist.name, dist.version))
    return [{'name': dist.name, 'version': dist.version} for dist in distributions]
