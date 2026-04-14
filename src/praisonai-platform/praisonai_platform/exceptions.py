"""Custom exception hierarchy for the platform package."""


class PlatformError(Exception):
    """Base exception for all platform errors."""
    
    def __init__(self, message: str = "A platform error occurred"):
        self.message = message
        super().__init__(message)


class NotFoundError(PlatformError):
    """Raised when a requested resource is not found (maps to HTTP 404)."""
    
    def __init__(self, message: str = "Resource not found"):
        super().__init__(message)


class DuplicateError(PlatformError):
    """Raised when a resource already exists (maps to HTTP 409)."""
    
    def __init__(self, message: str = "Resource already exists"):
        super().__init__(message)


class AuthenticationError(PlatformError):
    """Raised when authentication credentials are invalid (maps to HTTP 401)."""
    
    def __init__(self, message: str = "Authentication failed"):
        super().__init__(message)


class AuthorizationError(PlatformError):
    """Raised when user lacks sufficient permissions (maps to HTTP 403)."""
    
    def __init__(self, message: str = "Insufficient permissions"):
        super().__init__(message)


class ValidationError(PlatformError):
    """Raised when input data is invalid (maps to HTTP 422)."""
    
    def __init__(self, message: str = "Invalid input data"):
        super().__init__(message)