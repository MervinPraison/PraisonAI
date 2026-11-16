"""Helpers shared by AudioAgent, OCRAgent and VisionAgent (G-30).

The three agents had identical copies of these methods; they now inherit
this one. Each agent still sets ``_console``, ``llm``, ``api_key`` and
``base_url`` in its own ``__init__``.
"""

import logging
from typing import Any, Dict, Optional, Union

from praisonaiagents._logging import get_logger


class _MediaAgentHelpers:
    """Lazy console, litellm log levels and LiteLLM call parameters."""

    @property
    def console(self):
        """Lazily initialize Rich Console."""
        if self._console is None:
            from rich.console import Console
            self._console = Console()
        return self._console

    def _configure_logging(self, verbose: Union[bool, int]) -> None:
        """Configure logging levels."""
        if isinstance(verbose, int) and verbose >= 10:
            get_logger("litellm").setLevel(logging.DEBUG)
        else:
            get_logger("litellm").setLevel(logging.WARNING)
            get_logger("httpx").setLevel(logging.WARNING)

    def _get_model_params(self, model: Optional[str] = None) -> Dict[str, Any]:
        """Build parameters for LiteLLM calls."""
        params = {"model": model or self.llm}
        if self.api_key:
            params["api_key"] = self.api_key
        if self.base_url:
            params["api_base"] = self.base_url
        return params
