"""Exceptions for Logfire callers, including Agent Sandboxes checkout failures.

AgentSandboxError groups refusal and connection errors. AgentSandboxRefusedError exposes
the server's status and reason; AgentSandboxConnectionError reports transport failures.
Errors raised inside checked-out sessions are not wrapped.
"""


class AgentSandboxError(Exception):
    """Base class for Agent Sandboxes checkout errors."""


class AgentSandboxRefusedError(AgentSandboxError):
    """The server refused a checkout; the original Monty error is the chained cause.

    Attributes:
        status_code: The server's canonical gRPC status name, or None.
        status_message: The server's status message, or None.
        reason: The server's policy reason, copied from Monty's cause attribute, or None.
    """

    def __init__(
        self, message: str, *, status_code: str | None, status_message: str | None, reason: str | None
    ) -> None:
        self.status_code = status_code
        self.status_message = status_message
        self.reason = reason
        super().__init__(message)


class AgentSandboxConnectionError(AgentSandboxError):
    """The client could not reach the server or open a session."""


class LogfireConfigError(ValueError):
    """Error raised when there is a problem with the Logfire configuration."""


class LogfireServerWarning(UserWarning):
    """Warning emitted when the Logfire server returns an `X-Logfire-Warning` header on a response."""
