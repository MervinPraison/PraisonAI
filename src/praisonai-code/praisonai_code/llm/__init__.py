"""LLM endpoint and credential helpers for the agentic CLI (wrapper-independent)."""

from __future__ import annotations

from .catalogue import ModelCatalogue, ModelInfo
from .config import build_config_list
from .credentials import (
    inject_credentials_into_env,
    is_configured,
    resolve_llm_endpoint_with_credentials,
)
from .env import (
    LLMEndpoint,
    default_model_for_available_provider,
    resolve_llm_endpoint,
)

__all__ = [
    "LLMEndpoint",
    "ModelCatalogue",
    "ModelInfo",
    "build_config_list",
    "default_model_for_available_provider",
    "inject_credentials_into_env",
    "is_configured",
    "resolve_llm_endpoint",
    "resolve_llm_endpoint_with_credentials",
]
