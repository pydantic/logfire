"""Build hooks for the migration-safe SDK wheel layout."""

from typing import Any

from hatchling.builders.hooks.plugin.interface import BuildHookInterface


class CustomBuildHook(BuildHookInterface):
    """Keep editable installs linked to the source tree instead of copied."""

    def initialize(self, version: str, build_data: dict[str, Any]) -> None:
        """Override standard wheel inclusions when Hatch builds editable metadata."""
        if self.target_name == 'wheel' and version == 'editable':
            # A non-empty override prevents Hatch from copying the standard wheel's
            # normal and migration-fallback packages into editable environments.
            build_data['force_include_editable'] = {'logfire_sdk.pth': 'logfire_sdk.pth'}
