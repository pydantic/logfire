from functools import lru_cache

@lru_cache
def collect_package_info() -> dict[str, str]:
    """Retrieve the package information for all installed packages.

    Returns:
        A dict with the package name and version.
    """
