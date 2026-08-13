from enum import StrEnum


class ErrorKind(StrEnum):
    USER = "user"
    TRANSIENT = "transient"
    PROVIDER = "provider"
    SYSTEM = "system"


class ClipForgeError(Exception):
    code: str = "clipforge_error"
    kind: ErrorKind = ErrorKind.SYSTEM
    retryable: bool = False
    http_status: int = 500

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class UserError(ClipForgeError):
    """Invalid input from the caller. Retrying never helps."""

    kind = ErrorKind.USER
    http_status = 400


class AuthenticationError(UserError):
    code = "authentication_failed"
    http_status = 401


class ForbiddenError(UserError):
    code = "forbidden"
    http_status = 403


class EntityNotFoundError(UserError):
    code = "entity_not_found"
    http_status = 404


class ConflictError(UserError):
    code = "conflict"
    http_status = 409


class TransientError(ClipForgeError):
    """Infrastructure hiccup (DB/queue briefly down). Retrying may help."""

    kind = ErrorKind.TRANSIENT
    retryable = True
    http_status = 503


class ProviderError(ClipForgeError):
    """External AI/provider dependency failed. Circuit-breaker + retry."""

    kind = ErrorKind.PROVIDER
    retryable = True
    http_status = 503


class SystemError(ClipForgeError):
    """Internal bug or impossible state. Retrying will not help."""

    kind = ErrorKind.SYSTEM
    http_status = 500
