class LogfireConfigError(ValueError):
    """Error raised when there is a problem with the Logfire configuration."""
class LogfireServerWarning(UserWarning):
    """Warning emitted when the Logfire server returns an `X-Logfire-Warning` header on a response."""
