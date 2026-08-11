"""Lazy loader helpers for wrapper-only modules (C8.4 extraction target)."""

from __future__ import annotations


def get_inbuilt_tools():
    from praisonai import inbuilt_tools
    return inbuilt_tools


def get_generate_config():
    from praisonai.inc.config import generate_config
    return generate_config


def get_auto_generator():
    from praisonai.auto import AutoGenerator
    return AutoGenerator


def get_agents_generator():
    from praisonai.agents_generator import AgentsGenerator
    return AgentsGenerator


def get_call_module():
    try:
        from praisonai.api import call as call_module
    except ImportError as exc:
        raise ImportError(
            'Call feature is not installed. Install with: pip install "praisonai[call]"'
        ) from exc
    return call_module
