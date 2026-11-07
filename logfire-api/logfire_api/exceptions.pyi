class AgentSandboxError(Exception):
    """Base class for Agent Sandboxes checkout errors."""

class AgentSandboxRefusedError(AgentSandboxError):
    """The server refused a checkout; the original Monty error is the chained cause.

    Attributes:
        status_code: The server's canonical gRPC status name, or None.
        status_message: The server's status message, or None.
        reason: The server's policy reason, copied from Monty's cause attribute, or None.
    """
    status_code: str | None
    status_message: str | None
    reason: str | None
    def __init__(self, message: str, *, status_code: str | None = None, status_message: str | None = None, reason: str | None = None) -> None: ...

class AgentSandboxConnectionError(AgentSandboxError):
    """The client could not reach the server or open a session."""
class LogfireConfigError(ValueError):
    """Error raised when there is a problem with the Logfire configuration."""
class LogfireServerWarning(UserWarning):
    """Warning emitted when the Logfire server returns an `X-Logfire-Warning` header on a response."""
