from collections.abc import Mapping
from datetime import timedelta
from logfire.variables.abstract import VariableProvider, VariableResolutionDetails
from typing import Any

__all__ = ['LogfireRemoteVariableProvider']

class LogfireRemoteVariableProvider(VariableProvider):
    """Variable provider that fetches configuration from a remote Logfire API.

    The threading implementation draws heavily from opentelemetry.sdk._shared_internal.BatchProcessor.
    """
    def __init__(self, base_url: str, token: str, block_before_first_fetch: bool, polling_interval: timedelta | float = ...) -> None:
        """Create a new remote variable provider.

        Args:
            base_url: The base URL of the Logfire API.
            token: Authentication token for the Logfire API.
            block_before_first_fetch: Whether to block on first variable access until configuration
                is fetched from the remote API.
            polling_interval: How often to poll for configuration updates. Can be a timedelta or
                a number of seconds.
        """
    def refresh(self, force: bool = False):
        """Fetch the latest variable configuration from the remote API.

        Args:
            force: If True, fetch configuration even if the polling interval hasn't elapsed.
        """
    def get_serialized_value(self, variable_name: str, targeting_key: str | None = None, attributes: Mapping[str, Any] | None = None) -> VariableResolutionDetails[str | None]:
        """Resolve a variable's serialized value from the remote configuration.

        Args:
            variable_name: The name of the variable to resolve.
            targeting_key: Optional key for deterministic variant selection (e.g., user ID).
            attributes: Optional attributes for condition-based targeting rules.

        Returns:
            A VariableResolutionDetails containing the serialized value (or None if not found).
        """
    def shutdown(self) -> None:
        """Stop the background polling thread and clean up resources."""
