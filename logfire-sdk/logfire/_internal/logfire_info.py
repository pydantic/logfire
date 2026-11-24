"""Versions of Logfire and related packages for support reports."""

import platform
import sys

from ..version import VERSION


def logfire_info() -> str:
    """Show versions of logfire, OS and related packages."""
    import importlib.metadata as importlib_metadata

    # get data about packages that are closely related to logfire
    package_names = {
        # use by otel to send data
        'requests': 1,
        # custom integration
        'pydantic': 2,
        # otel integration is customed
        'fastapi': 3,
        # custom integration
        'openai': 4,
        # dependencies of otel
        'protobuf': 5,
        # dependencies
        'rich': 6,
        # dependencies
        'typing-extensions': 7,
        # dependencies
        'tomli': 8,
        # dependencies
        'executing': 9,
    }
    otel_index = max(package_names.values(), default=0) + 1
    related_packages: list[tuple[int, str, str]] = []

    for dist in importlib_metadata.distributions():
        metadata = dist.metadata
        name = metadata.get('Name', '')
        version = metadata.get('Version', 'UNKNOWN')
        index = package_names.get(name)
        if index is not None:
            related_packages.append((index, name, version))
        if name.startswith('opentelemetry'):
            related_packages.append((otel_index, name, version))

    toml_lines: tuple[str, ...] = (
        f'logfire="{VERSION}"',
        f'platform="{platform.platform()}"',
        f'python="{sys.version}"',
        '[related_packages]',
        *(f'{name}="{version}"' for _, name, version in sorted(related_packages)),
    )
    return '\n'.join(toml_lines) + '\n'
