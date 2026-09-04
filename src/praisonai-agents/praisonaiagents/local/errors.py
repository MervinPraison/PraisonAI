"""Exceptions raised by praisonaiagents.local.

Deliberately NOT subclasses of praisonaiagents.errors: this package imports
nothing from praisonaiagents, and wrapping is the integration layer's job.
"""

from __future__ import annotations

__all__ = ["LocalError", "NoLocalEngineError", "EngineUnreachableError",
           "HostHeaderRejectedError", "ModelNotAvailableError",
           "InvalidLocalSpecError"]


class LocalError(Exception):
    """Base class for every error raised by praisonaiagents.local.

    Deliberately not a subclass of praisonaiagents.errors: this package imports
    nothing from praisonaiagents, and wrapping is the integration layer's job.
    """


class NoLocalEngineError(LocalError):
    """No local model server could be found or was named."""


class EngineUnreachableError(LocalError):
    """An explicitly named local server did not answer."""

    def __init__(self, message, base_url="", reason="", source=""):
        super().__init__(message)
        self.base_url = base_url
        self.reason = reason
        self.source = source


class HostHeaderRejectedError(EngineUnreachableError):
    """The server returned a bodyless 403 because the Host header was not local."""


class ModelNotAvailableError(LocalError):
    def __init__(self, message, model_id="", available=()):
        super().__init__(message)
        self.model_id = model_id
        self.available = tuple(available)


class InvalidLocalSpecError(LocalError, ValueError):
    """The spec string could not be parsed."""
