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
    has_provider_credential,
    resolve_llm_endpoint,
)
from .local_detect import LocalModel, detect_local_model

__all__ = [
    "LLMEndpoint",
    "LocalModel",
    "ModelCatalogue",
    "ModelInfo",
    "build_config_list",
    "default_model_for_available_provider",
    "detect_local_model",
    "has_provider_credential",
    "inject_credentials_into_env",
    "is_configured",
    "resolve_llm_endpoint",
    "resolve_llm_endpoint_with_credentials",
]
