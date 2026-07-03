"""C7.1 boundary tests — wrapper bridge and import gate."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[4]


def test_wrapper_bridge_import_module_requires_wrapper():
    from praisonai_code._wrapper_bridge import import_wrapper_module, wrapper_available

    if not wrapper_available():
        with pytest.raises(ImportError, match="pip install praisonai"):
            import_wrapper_module("praisonai.framework_adapters.registry")
    else:
        mod = import_wrapper_module("praisonai.framework_adapters.registry")
        assert hasattr(mod, "get_default_registry")


def test_main_framework_helpers_use_bridge():
    from praisonai_code.cli.main import _fw_registry_module, _fw_validators_module

    if not importlib.util.find_spec("praisonai"):
        with pytest.raises(ImportError, match="pip install praisonai"):
            _fw_registry_module()
    else:
        assert hasattr(_fw_registry_module(), "get_default_registry")
        assert hasattr(_fw_validators_module(), "assert_framework_available")


def test_c7_import_gate_script_passes():
    result = subprocess.run(
        ["bash", "scripts/check_c7_imports.sh"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_doctor_skip_without_wrapper():
    from praisonai_code._wrapper_bridge import wrapper_available
    from praisonai_code.cli.features.doctor.checks._wrapper_checks import skip_if_no_wrapper
    from praisonai_code.cli.features.doctor.models import CheckStatus

    if wrapper_available():
        assert skip_if_no_wrapper("test", "Test") is None
    else:
        result = skip_if_no_wrapper("test", "Test")
        assert result is not None
        assert result.status == CheckStatus.SKIP


def test_recipe_creator_importable_without_wrapper():
    """RecipeCreator must not load wrapper auto constants at import time."""
    import praisonai_code.cli.features.recipe_creator as rc

    assert hasattr(rc, "RecipeCreator")


def test_capabilities_cap_uses_bridge():
    from praisonai_code.cli.features.capabilities import _cap
    from praisonai_code._wrapper_bridge import wrapper_available

    if wrapper_available():
        fn = _cap("audio", "transcribe")
        assert callable(fn)


def test_serve_doctor_skips_without_wrapper():
    from praisonai_code._wrapper_bridge import wrapper_available
    from praisonai_code.cli.features.doctor.checks.serve_checks import check_serve_module
    from praisonai_code.cli.features.doctor.models import CheckStatus, DoctorConfig

    if not wrapper_available():
        result = check_serve_module(DoctorConfig())
        assert result.status == CheckStatus.SKIP


def test_wrapper_resident_commands_resolve_when_wrapper_installed():
    """Each _WRAPPER_RESIDENT command loads from praisonai.cli.commands.*."""
    from praisonai_code._wrapper_bridge import wrapper_available
    from praisonai_code.cli.app import _WRAPPER_RESIDENT_COMMANDS

    if not wrapper_available():
        pytest.skip("requires praisonai wrapper installed")

    import importlib

    # Commands without a Typer ``app`` (inline or click-only wiring in code app.py)
    _skip_app_attr = frozenset({"standardise", "app", "audit"})

    for name in sorted(_WRAPPER_RESIDENT_COMMANDS):
        if name in _skip_app_attr:
            continue
        mod = importlib.import_module(f"praisonai.cli.commands.{name}")
        assert hasattr(mod, "app"), f"praisonai.cli.commands.{name} must expose Typer app"

def test_run_file_crewai_requires_wrapper():
    """Multi-framework YAML is wrapper-enhanced; standalone must fail clearly."""
    from praisonai_code._wrapper_bridge import wrapper_available

    if wrapper_available():
        pytest.skip("requires standalone env without praisonai wrapper")

    import subprocess
    import tempfile

    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as f:
        f.write("framework: crewai\nagents: []\n")
        yaml_path = f.name

    result = subprocess.run(
        ["praisonai-code", "run", "--file", yaml_path, "hello"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    combined = result.stdout + result.stderr
    assert result.returncode != 0
    assert "pip install praisonai" in combined.lower() or "import" in combined.lower()


def test_c8_hybrid_module_imports():
    """Critical repatriated / hybrid paths must resolve when wrapper is installed."""
    import importlib

    from praisonai_code._wrapper_bridge import wrapper_available

    if not wrapper_available():
        pytest.skip("requires praisonai wrapper installed")

    paths = [
        ("praisonai.cli.features.tui.app", "TUIApp"),
        ("praisonai.cli.features.tools", "ToolsHandler"),
        ("praisonai.cli.features.workflow", "WorkflowHandler"),
        ("praisonai.cli.interactive.core", "InteractiveCore"),
        ("praisonai_code.cli.interactive.async_tui", "AsyncTUI"),
        ("praisonai_code.cli.features.workflow", "WorkflowHandler"),
    ]
    for module_name, attr in paths:
        mod = importlib.import_module(module_name)
        assert hasattr(mod, attr), f"{module_name} missing {attr}"


def test_textual_frontend_tui_app_import():
    """TextualFrontend.run() must resolve TUIApp via hybrid wrapper package."""
    import importlib

    from praisonai_code._wrapper_bridge import wrapper_available

    if not wrapper_available():
        pytest.skip("requires praisonai wrapper installed")

    mod = importlib.import_module(
        "praisonai_code.cli.interactive.frontends.textual_frontend"
    )
    source = importlib.import_module("inspect").getsource(mod.TextualFrontend.run)
    assert "import_wrapper_module" in source
    assert "praisonai.cli.features.tui.app" in source
