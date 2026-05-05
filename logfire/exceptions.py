"""Logfire exceptions."""


class LogfireConfigError(ValueError):
    """Error raised when there is a problem with the Logfire configuration."""


class LogfireServerError(Exception):
    """Error raised when the Logfire server returns an `X-Logfire-Error` header on a response."""


class LogfireServerWarning(UserWarning):
    """Warning emitted when the Logfire server returns an `X-Logfire-Warning` header on a response."""
