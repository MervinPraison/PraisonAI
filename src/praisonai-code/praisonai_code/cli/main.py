# praisonai/cli/main.py — thin re-export layer (C8.4)

import sys
import argparse
import warnings
import os
import json
import logging
import importlib

from ._warnings import install_warning_filters, _uninstall_warning_filters, _SUPPRESSED_PATTERNS
from praisonai_code._version import get_package_version

__version__ = get_package_version()

if os.environ.get('LOGLEVEL', 'INFO').upper() != 'DEBUG':
    warnings.filterwarnings(
        "ignore",
        message=".*found in sys.modules after import of package.*",
        category=RuntimeWarning
    )

from .legacy.env_security import (
    _BLOCKED_ENV_KEYS,
    _BLOCKED_ENV_KEYS_UPPER,
    _load_env_once,
    _validate_env_key,
)
from .legacy.praison_ai import PraisonAI

from praisonai_code._framework_availability import is_available

_AVAILABILITY_FLAGS = {
    "GRADIO_AVAILABLE": "gradio",
    "CREWAI_AVAILABLE": "crewai",
    "AUTOGEN_AVAILABLE": "autogen",
    "PRAISONAI_AVAILABLE": "praisonaiagents",
    "TRAIN_AVAILABLE": "unsloth",
}


def _compute_availability_flag(name):
    if name in _AVAILABILITY_FLAGS:
        return is_available(_AVAILABILITY_FLAGS[name])
    if name == "CALL_MODULE_AVAILABLE":
        try:
            import importlib.util
            return importlib.util.find_spec("praisonai.api.call") is not None
        except (ModuleNotFoundError, AttributeError):
            return False
    raise AttributeError(name)


def _ensure_availability_flags():
    g = globals()
    for flag in (*_AVAILABILITY_FLAGS, "CALL_MODULE_AVAILABLE"):
        if flag not in g:
            g[flag] = _compute_availability_flag(flag)


def __getattr__(name):
    if name in _AVAILABILITY_FLAGS or name == "CALL_MODULE_AVAILABLE":
        value = _compute_availability_flag(name)
        globals()[name] = value
        return value
    raise AttributeError(name)


def _get_inbuilt_tools():
    from praisonai_code._wrapper_bridge import import_wrapper_module
    return import_wrapper_module("praisonai.cli.legacy.inbuilt_tools").get_inbuilt_tools()


def _get_generate_config():
    from praisonai_code._wrapper_bridge import import_wrapper_module
    return import_wrapper_module("praisonai.cli.legacy.inbuilt_tools").get_generate_config()


def _get_auto_generator():
    from praisonai_code._wrapper_bridge import import_wrapper_module
    return import_wrapper_module("praisonai.cli.legacy.inbuilt_tools").get_auto_generator()


def _get_agents_generator():
    from praisonai_code._wrapper_bridge import import_wrapper_module
    return import_wrapper_module("praisonai.cli.legacy.inbuilt_tools").get_agents_generator()


def _get_call_module():
    import importlib.util
    if not importlib.util.find_spec("praisonai.api.call"):
        raise ImportError(
            'Call feature is not installed. Install with: pip install "praisonai[call]"'
        )
    from praisonai_code._wrapper_bridge import import_wrapper_module
    _mod = import_wrapper_module("praisonai.api")
    return getattr(_mod, "call")


def _fw_registry_module():
    from praisonai_code._wrapper_bridge import import_wrapper_module
    return import_wrapper_module("praisonai.framework_adapters.registry")


def _fw_validators_module():
    from praisonai_code._wrapper_bridge import import_wrapper_module
    return import_wrapper_module("praisonai.framework_adapters.validators")


def _fw_workflow_module():
    from praisonai_code._wrapper_bridge import import_wrapper_module
    return import_wrapper_module("praisonai.framework_adapters.workflow_framework")


def _provider_preflight_message():
    try:
        from praisonai_code.llm.credentials import inject_credentials_into_env, is_configured
        inject_credentials_into_env()
        runtime_model = os.environ.get("MODEL_NAME") or os.environ.get("OPENAI_MODEL_NAME")
        if is_configured(model=runtime_model):
            return None
    except Exception:
        return None
    return (
        "No LLM provider is configured.\n\n"
        "PraisonAI supports OpenAI, Anthropic, Google/Gemini, Groq, "
        "Cohere, Ollama, OpenRouter and 100+ models via LiteLLM.\n\n"
        "Easiest setup (interactive, no shell 'export' needed):\n"
        "    praisonai setup\n\n"
        "Or set a provider API key, for example:\n"
        "    export OPENAI_API_KEY=...        # OpenAI\n"
        "    export ANTHROPIC_API_KEY=...     # Anthropic Claude\n"
        "    export GEMINI_API_KEY=...        # Google Gemini\n"
    )


def stream_subprocess(command, env=None):
    """Execute a subprocess and stream output to the terminal."""
    import subprocess
    from rich import print
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        universal_newlines=True,
        env=env,
    )
    for line in iter(process.stdout.readline, ''):
        print(line, end='')
        sys.stdout.flush()
    process.stdout.close()
    return_code = process.wait()
    if return_code != 0:
        raise subprocess.CalledProcessError(return_code, command)


if __name__ == "__main__":
    install_warning_filters()
    praison_ai = PraisonAI()
    praison_ai.main()
