#!/usr/bin/env python3
"""C8.4 — mechanical main.py decomposition into legacy modules."""

from __future__ import annotations

import re
import textwrap
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
MAIN = REPO / "src/praisonai-code/praisonai_code/cli/main.py"
CODE_LEGACY = REPO / "src/praisonai-code/praisonai_code/cli/legacy"
WRAP_LEGACY = REPO / "src/praisonai/praisonai/cli/legacy"
PRAISON_AI = CODE_LEGACY / "praison_ai.py"
THIN_MAIN = MAIN

# (start, end) 1-indexed inclusive
RANGES = {
    "env_security.py": (45, 92),
    "subcommand_handlers.py": [
        (2342, 2518),  # memory
        (2520, 2631),  # rules
        (3310, 3392),  # hooks
        (3394, 3479),  # knowledge (stop before session)
        (3535, 3647),  # docs
        (3649, 3808),  # mcp
        (3810, 3907),  # sensitive patterns + check + clean_commit
        (3909, 4119),  # commit
        (5761, 5803),  # context
        (5805, 6010),  # research
    ],
    "workflow_commands.py": (2633, 3308),
    "direct_prompt.py": [
        (2087, 2340),
        (4121, 4148),  # _save_output
        (4421, 5385),
    ],
    "dispatch/argparse_builder.py": (1074, 1359),
    "interactive_legacy.py": (6012, 7486),
}

# Lines to remove from praison_ai (replaced by delegation)
EXTRACT_LINES = set()
for spec in RANGES.values():
    blocks = spec if isinstance(spec, list) else [spec]
    for start, end in blocks:
        EXTRACT_LINES.update(range(start, end + 1))

DELEGATE_METHODS = {
    "subcommand_handlers": [
        "handle_memory_command",
        "handle_rules_command",
        "handle_hooks_command",
        "handle_knowledge_command",
        "handle_docs_command",
        "handle_mcp_command",
        "handle_commit_command",
        "handle_context_command",
        "handle_research_command",
        "_check_sensitive_content",
        "_clean_commit_message",
        "_get_sensitive_patterns",
    ],
    "workflow_commands": [
        "handle_workflow_command",
        "_run_yaml_workflow",
        "_validate_yaml_workflow",
        "_get_canonical_suggestions",
        "_create_workflow_from_template",
        "_auto_generate_workflow",
    ],
    "direct_prompt": [
        "_rewrite_query",
        "_rewrite_query_if_enabled",
        "_expand_prompt",
        "_expand_prompt_if_enabled",
        "_load_tools",
        "_load_toolsets",
        "_save_output",
        "handle_direct_prompt",
    ],
    "interactive_legacy": [
        "_start_interactive_mode",
        "_load_interactive_tools",
        "_run_chat_mode",
    ],
}


def read_lines() -> list[str]:
    return MAIN.read_text(encoding="utf-8").splitlines(keepends=True)


def dedent_block(lines: list[str], spaces: int = 4) -> list[str]:
    out: list[str] = []
    prefix = " " * spaces
    for line in lines:
        if line.startswith(prefix):
            out.append(line[spaces:])
        else:
            out.append(line)
    return out


def extract_range(all_lines: list[str], start: int, end: int) -> list[str]:
    return dedent_block(all_lines[start - 1 : end])


def transform_sensitive_patterns(lines: list[str]) -> list[str]:
    text = "".join(lines)
    text = text.replace("cls._SENSITIVE_PATTERNS", "_SENSITIVE_PATTERNS")
    text = re.sub(
        r"@classmethod\s*\n\s*def _get_sensitive_patterns\(cls\):",
        "def _get_sensitive_patterns():",
        text,
    )
    text = text.replace("    _SENSITIVE_PATTERNS = None\n", "_SENSITIVE_PATTERNS = None\n")
    text = text.replace("    _SENSITIVE_FILES = ", "_SENSITIVE_FILES = ")
    text = text.replace("    _SENSITIVE_EXTENSIONS = ", "_SENSITIVE_EXTENSIONS = ")
    text = text.replace("self._get_sensitive_patterns()", "_get_sensitive_patterns()")
    text = re.sub(
        r"@staticmethod\s*\n\s*def _clean_commit_message",
        "def _clean_commit_message",
        text,
    )
    return text.splitlines(keepends=True)


def module_header(doc: str, extra_imports: str = "") -> str:
    return textwrap.dedent(
        f'''\
        """{doc}"""

        from __future__ import annotations

        import argparse
        import json
        import logging
        import os
        import shutil
        import subprocess
        import sys
        import time
        import yaml
        from dotenv import load_dotenv
        from rich import print
        {extra_imports}
        '''
    )


def write_env_security(all_lines: list[str]) -> None:
    body = all_lines[44:92]  # module-level — no dedent
    header = '"""Environment variable security (C8.4)."""\n\nfrom __future__ import annotations\n\nfrom dotenv import load_dotenv\n\n'
    path = CODE_LEGACY / "env_security.py"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(header + "".join(body), encoding="utf-8")


def write_subcommand_handlers(all_lines: list[str]) -> None:
    parts: list[str] = []
    for start, end in RANGES["subcommand_handlers.py"]:  # type: ignore[index]
        chunk = extract_range(all_lines, start, end)
        if start == 3810:
            chunk = transform_sensitive_patterns(chunk)
        parts.append("".join(chunk))
    content = module_header("CLI subcommand handlers (C8.4).") + "\n".join(parts)
    path = WRAP_LEGACY / "subcommand_handlers.py"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def write_workflow_commands(all_lines: list[str]) -> None:
    start, end = RANGES["workflow_commands.py"]  # type: ignore[misc]
    body = extract_range(all_lines, start, end)
    content = module_header("Workflow CLI commands (C8.4).") + "".join(body)
    path = WRAP_LEGACY / "workflow_commands.py"
    path.write_text(content, encoding="utf-8")


def write_direct_prompt(all_lines: list[str]) -> None:
    parts: list[str] = []
    for start, end in RANGES["direct_prompt.py"]:  # type: ignore[index]
        parts.append("".join(extract_range(all_lines, start, end)))
    content = module_header("Direct prompt execution (C8.4).") + "\n".join(parts)
    path = WRAP_LEGACY / "direct_prompt.py"
    path.write_text(content, encoding="utf-8")


def write_argparse_builder(all_lines: list[str]) -> None:
    body = dedent_block(all_lines[1073:1359], spaces=8)
    fn = textwrap.dedent(
        '''\

        def build_argument_parser(in_test_env: bool):
            """Build ArgumentParser and parse argv. Returns (args, unknown_args, special_commands)."""
            special_commands = ['chat', 'code', 'call', 'realtime', 'train', 'ui', 'context', 'research', 'memory', 'rules', 'workflow', 'hooks', 'knowledge', 'session', 'tools', 'todo', 'docs', 'mcp', 'commit', 'serve', 'schedule', 'skills', 'profile', 'eval', 'agents', 'run', 'thinking', 'compaction', 'output', 'deploy', 'templates', 'recipe', 'endpoints', 'audio', 'embed', 'embedding', 'images', 'moderate', 'files', 'batches', 'vector-stores', 'rerank', 'ocr', 'assistants', 'fine-tuning', 'completions', 'messages', 'guardrails', 'rag', 'videos', 'a2a', 'containers', 'passthrough', 'responses', 'search', 'realtime-api', 'doctor', 'registry', 'package', 'install', 'uninstall', 'acp', 'debug', 'lsp', 'diag', 'browser', 'replay', 'bot', 'gateway', 'sandbox', 'wizard', 'migrate', 'security', 'persistence', 'paths', 'claw', 'github', 'managed', 'flow', 'dashboard', 'backends', 'audit']

        '''
    )
    # Replace first two lines (special_commands + blank) from body — body starts with special_commands
    body_text = "".join(body)
    body_text = re.sub(
        r"^\s*special_commands = \[.*?\]\s*\n\s*\n",
        "",
        body_text,
        count=1,
        flags=re.DOTALL,
    )
    indented = textwrap.indent(body_text, "    ")
    parse_tail = textwrap.indent(
        textwrap.dedent(
            """
            if in_test_env:
                args, unknown_args = parser.parse_known_args([])
            else:
                args, unknown_args = parser.parse_known_args()
            return args, unknown_args, special_commands
            """
        ),
        "    ",
    )
    extra = "from praisonai.cli.legacy.framework_run import fw_registry_module as _fw_registry_module\n"
    content = (
        module_header("ArgumentParser schema for legacy CLI (C8.4).", extra)
        + fn
        + indented
        + parse_tail
    )
    path = WRAP_LEGACY / "dispatch" / "argparse_builder.py"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def write_interactive_legacy(all_lines: list[str]) -> None:
    start, end = RANGES["interactive_legacy.py"]  # type: ignore[misc]
    body = extract_range(all_lines, start, end)
    content = module_header("Interactive REPL/TUI legacy path (C8.4).") + "".join(body)
    path = WRAP_LEGACY / "interactive_legacy.py"
    path.write_text(content, encoding="utf-8")


def make_delegate(module_suffix: str, method: str) -> str:
    mod = f"praisonai.cli.legacy.{module_suffix}"
    return (
        f"    def {method}(self, *args, **kwargs):\n"
        f'        from praisonai_code._wrapper_bridge import import_wrapper_module\n'
        f'        _mod = import_wrapper_module("{mod}")\n'
        f'        return getattr(_mod, "{method}")(self, *args, **kwargs)\n\n'
    )


def write_praison_ai(all_lines: list[str]) -> None:
    kept: list[str] = []
    for i, line in enumerate(all_lines):
        line_no = i + 1
        if line_no < 347:
            continue
        if line_no in EXTRACT_LINES:
            continue
        kept.append(line)

    text = "".join(kept)

    # Replace argparse builder block inside parse_args
    text = re.sub(
        r"        # Define special commands\n        special_commands = \[.*?"
        r"            args, unknown_args = parser\.parse_known_args\(\)\n\n",
        "        from praisonai_code._wrapper_bridge import import_wrapper_module\n"
        "        _ab = import_wrapper_module(\"praisonai.cli.legacy.dispatch.argparse_builder\")\n"
        "        args, unknown_args, special_commands = _ab.build_argument_parser(in_test_env)\n\n",
        text,
        count=1,
        flags=re.DOTALL,
    )

    # Remove dead branches in special_commands block (already handled earlier)
    text = re.sub(
        r"\n            elif args\.command == 'call':\n"
        r"                import importlib\.util\n.*?"
        r"                sys\.exit\(0\)\n",
        "\n",
        text,
        count=1,
        flags=re.DOTALL,
    )
    text = re.sub(
        r"\n            elif args\.command == 'serve':\n"
        r"                # Serve command.*?\n                sys\.exit\(exit_code\)\n",
        "\n",
        text,
        count=1,
        flags=re.DOTALL,
    )
    text = re.sub(
        r"\n            elif args\.command == 'replay':\n"
        r"                # Replay command.*?\n                sys\.exit\(0\)\n",
        "\n",
        text,
        count=1,
        flags=re.DOTALL,
    )

    delegates = ""
    for mod, methods in DELEGATE_METHODS.items():
        for method in methods:
            delegates += make_delegate(mod, method)

    # Insert delegates at end of PraisonAI class (before trailing module-level code)
    text = text.rstrip() + "\n\n" + delegates

    header = textwrap.dedent(
        '''\
        """PraisonAI CLI class — C8.4 legacy shell."""

        from __future__ import annotations

        import sys
        import argparse
        import warnings
        import os
        import json
        import yaml
        import time
        from rich import print
        from dotenv import load_dotenv
        import shutil
        import subprocess
        import logging
        import importlib

        from praisonai_code._version import get_package_version
        from praisonai_code._framework_availability import is_available
        from praisonai_code._logging import configure_cli_logging
        from .legacy.env_security import (
            _BLOCKED_ENV_KEYS,
            _BLOCKED_ENV_KEYS_UPPER,
            _load_env_once,
            _validate_env_key,
        )

        __version__ = get_package_version()

        if os.environ.get('LOGLEVEL', 'INFO').upper() != 'DEBUG':
            warnings.filterwarnings(
                "ignore",
                message=".*found in sys.modules after import of package.*",
                category=RuntimeWarning
            )

        '''
    )

    helpers = "".join(all_lines[94:173]) + "".join(all_lines[228:346])
    helpers = helpers.replace(
        'return import_wrapper_module("praisonai.inbuilt_tools")',
        'return import_wrapper_module("praisonai.cli.legacy.inbuilt_tools")',
    )
    avail_section = "".join(all_lines[174:227])

    praison_content = header + helpers + avail_section + text
    PRAISON_AI.parent.mkdir(parents=True, exist_ok=True)
    PRAISON_AI.write_text(praison_content, encoding="utf-8")


def write_thin_main() -> None:
    content = textwrap.dedent(
        '''\
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
            return import_wrapper_module("praisonai.cli.legacy.inbuilt_tools")


        def _get_generate_config():
            from praisonai_code._wrapper_bridge import import_wrapper_module
            _mod = import_wrapper_module("praisonai.inc.config")
            return getattr(_mod, "generate_config")


        def _get_auto_generator():
            from praisonai_code._wrapper_bridge import import_wrapper_module
            _mod = import_wrapper_module("praisonai.auto")
            return getattr(_mod, "AutoGenerator")


        def _get_agents_generator():
            from praisonai_code._wrapper_bridge import import_wrapper_module
            _mod = import_wrapper_module("praisonai.agents_generator")
            return getattr(_mod, "AgentsGenerator")


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
                "No LLM provider is configured.\\n\\n"
                "PraisonAI supports OpenAI, Anthropic, Google/Gemini, Groq, "
                "Cohere, Ollama, OpenRouter and 100+ models via LiteLLM.\\n\\n"
                "Easiest setup (interactive, no shell 'export' needed):\\n"
                "    praisonai setup\\n\\n"
                "Or set a provider API key, for example:\\n"
                "    export OPENAI_API_KEY=...        # OpenAI\\n"
                "    export ANTHROPIC_API_KEY=...     # Anthropic Claude\\n"
                "    export GEMINI_API_KEY=...        # Google Gemini\\n"
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
        '''
    )
    THIN_MAIN.write_text(content, encoding="utf-8")


def main() -> None:
    all_lines = read_lines()
    write_env_security(all_lines)
    write_subcommand_handlers(all_lines)
    write_workflow_commands(all_lines)
    write_direct_prompt(all_lines)
    write_argparse_builder(all_lines)
    write_interactive_legacy(all_lines)
    write_praison_ai(all_lines)
    write_thin_main()
    print("C8.4 decomposition complete.")


if __name__ == "__main__":
    main()
