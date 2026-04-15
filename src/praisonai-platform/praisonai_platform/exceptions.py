"""Custom exceptions for the PraisonAI Platform."""


class PlatformError(Exception):
    """Base exception for all platform errors."""


class NotFoundError(PlatformError):
    """Resource not found."""


class DuplicateError(PlatformError):
    """Duplicate resource (e.g. email already registered)."""


class AuthenticationError(PlatformError):
    """Authentication failed (bad credentials or token)."""


class AuthorizationError(PlatformError):
    """Insufficient permissions for the requested action."""


class ValidationError(PlatformError):
    """Invalid input data."""
