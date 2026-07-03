"""Shared helpers for integration smoke scripts."""

from __future__ import annotations

import os


def pick_smoke_model() -> str:
    """Resolve a working LLM for smoke tests (honours TEST_MODEL, then Agent defaults)."""
    override = os.environ.get("TEST_MODEL") or os.environ.get("OPENAI_MODEL_NAME")
    if override:
        return override
    from praisonaiagents.agent.agent import Agent

    return Agent._resolve_default_model()
