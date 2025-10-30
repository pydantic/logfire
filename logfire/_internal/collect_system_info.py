from __future__ import annotations

import importlib.metadata as metadata
from functools import lru_cache


@lru_cache
def collect_package_info() -> dict[str, str]:
    """Retrieve the package information for all installed packages.

    Returns:
        A dicts with the package name and version.
    """
    try:
        distributions = list(metadata.distributions())
        try:
            metas = [dist.metadata for dist in distributions]
            pairs = [
                (getattr(meta, 'Name', '') or '', getattr(meta, 'Version', 'UNKNOWN') or 'UNKNOWN')
                for meta in metas
                if getattr(meta, 'Name', None)
            ]
        except Exception:  # pragma: no cover
            pairs = [(dist.name, dist.version) for dist in distributions]
    except Exception:  # pragma: no cover
        # Don't crash for this.
        pairs = []

    return dict(sorted(pairs))
