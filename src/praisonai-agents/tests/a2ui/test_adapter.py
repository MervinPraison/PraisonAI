"""Tests for A2UI adapter (optional a2ui-agent-sdk dependency)."""

import pytest


class TestA2UIAdapterImport:
    def test_a2ui_class_export(self):
        from praisonaiagents.ui.a2ui import A2UI

        assert A2UI is not None
        assert hasattr(A2UI, "create_part")

    def test_ui_lazy_a2ui_export(self):
        from praisonaiagents.ui import A2UI

        assert A2UI is not None

    def test_missing_optional_dep_raises_clear_error(self):
        pytest.importorskip("a2ui", reason="a2ui-agent-sdk not installed")
        # If installed, adapter imports should work
        from praisonaiagents.ui.a2ui.adapter import create_a2ui_part

        part = create_a2ui_part({"createSurface": {"surfaceId": "main", "catalogId": "test"}})
        assert part is not None


class TestA2UITool:
    def test_send_a2ui_messages_requires_sdk(self):
        from praisonaiagents.tools.a2ui_tools import send_a2ui_messages

        if pytest.importorskip("a2ui", reason="skip without sdk"):
            result = send_a2ui_messages(
                messages=[{"createSurface": {"surfaceId": "x", "catalogId": "c"}}]
            )
            assert result["mime_type"] == "application/json+a2ui"
            assert len(result["messages"]) == 1


class TestA2UIAdapterSmoke:
    def test_is_a2ui_part_with_sdk(self):
        pytest.importorskip("a2ui", reason="a2ui-agent-sdk not installed")
        from praisonaiagents.ui.a2ui.adapter import create_a2ui_part, is_a2ui_part

        part = create_a2ui_part({"messages": [{"createSurface": {"surfaceId": "m"}}]})
        assert is_a2ui_part(part) is True

    def test_create_a2ui_part_without_a2a_parts_module(self, monkeypatch):
        pytest.importorskip("a2ui", reason="a2ui-agent-sdk not installed")
        from praisonaiagents.ui.a2ui import adapter

        def _fake_import(name: str):
            if name in ("a2ui.a2a.parts", "a2ui.a2a"):
                raise ImportError("no a2a module in SDK 0.12")
            import importlib

            return importlib.import_module(name)

        monkeypatch.setattr(adapter, "_import", _fake_import)

        part = adapter.create_a2ui_part(
            {"createSurface": {"surfaceId": "main", "catalogId": "basic"}}
        )
        assert adapter.is_a2ui_part(part) is True

        from praisonaiagents.tools.a2ui_tools import send_a2ui_messages

        result = send_a2ui_messages(
            messages=[{"createSurface": {"surfaceId": "x", "catalogId": "c"}}]
        )
        assert result["mime_type"] == "application/json+a2ui"

    def test_missing_sdk_import_error_message(self):
        from unittest.mock import patch

        from praisonaiagents.ui.a2ui import adapter

        def _raise(_name):
            raise ImportError(
                "A2UI support requires the optional dependency. "
                "Install with: pip install praisonaiagents[a2ui]"
            )

        with patch.object(adapter, "_import", side_effect=_raise):
            with patch.object(adapter.importlib.util, "find_spec", return_value=None):
                with pytest.raises(ImportError, match="praisonaiagents\\[a2ui\\]"):
                    adapter.create_a2ui_part({"messages": []})

    def test_newer_sdk_without_a2a_module_still_returns_a_part(self):
        from unittest.mock import patch

        from praisonaiagents.ui.a2ui import adapter

        def find_spec(name):
            if name == "a2ui":
                return object()
            return None

        with patch.object(adapter.importlib.util, "find_spec", side_effect=find_spec):
            part = adapter.create_a2ui_part({"messages": [{"createSurface": {"surfaceId": "main"}}]})
        assert part.root.data["messages"][0]["createSurface"]["surfaceId"] == "main"
        assert part.root.metadata["mimeType"] == "application/json+a2ui"
        assert adapter.is_a2ui_part(part) is True


def test_public_tool_with_missing_a2a_parent_in_real_package_layout(tmp_path, monkeypatch):
    import subprocess
    import sys

    # A separate interpreter uses real importlib instead of a mocked find_spec.
    package = tmp_path / "a2ui"
    package.mkdir()
    (package / "__init__.py").write_text("")
    code = (
        "from praisonaiagents.tools.a2ui_tools import send_a2ui_messages; "
        "result = send_a2ui_messages([{\"createSurface\": {\"surfaceId\": \"main\"}}]); "
        "assert result[\"mime_type\"] == \"application/json+a2ui\""
    )
    import os
    from pathlib import Path
    env = os.environ.copy()
    env["PYTHONPATH"] = str(tmp_path) + os.pathsep + str(Path(__file__).resolve().parents[2])
    subprocess.run([sys.executable, "-c", code], env=env, check=True)


def test_missing_transitive_import_in_existing_a2a_package_is_not_hidden(tmp_path, monkeypatch):
    import subprocess
    import sys
    import os
    from pathlib import Path

    package = tmp_path / "a2ui" / "a2a"
    package.mkdir(parents=True)
    (package.parent / "__init__.py").write_text("")
    (package / "__init__.py").write_text("import missing_a2ui_transitive_dependency\n")
    code = (
        "from praisonaiagents.ui.a2ui.adapter import create_a2ui_part; "
        "create_a2ui_part({})"
    )
    env = os.environ.copy()
    env["PYTHONPATH"] = str(tmp_path) + os.pathsep + str(Path(__file__).resolve().parents[2])
    result = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True)
    assert result.returncode != 0
    assert "missing_a2ui_transitive_dependency" in result.stderr


def test_existing_a2a_helper_is_used(tmp_path):
    import os
    import subprocess
    import sys
    from pathlib import Path

    package = tmp_path / "a2ui" / "a2a"
    package.mkdir(parents=True)
    (package.parent / "__init__.py").write_text("")
    (package / "__init__.py").write_text("")
    (package / "parts.py").write_text("def create_a2ui_part(data): return (\"legacy\", data)\n")
    env = os.environ.copy()
    env["PYTHONPATH"] = str(tmp_path) + os.pathsep + str(Path(__file__).resolve().parents[2])
    code = "from praisonaiagents.ui.a2ui.adapter import create_a2ui_part; assert create_a2ui_part({}) == (\"legacy\", {})"
    subprocess.run([sys.executable, "-c", code], env=env, check=True)


def test_modern_sdk_parser_reports_unsupported_layout(monkeypatch):
    from types import SimpleNamespace
    from praisonaiagents.ui.a2ui import adapter

    monkeypatch.setattr(adapter, "_import", lambda name: SimpleNamespace())
    with pytest.raises(NotImplementedError, match="legacy response parser"):
        adapter.parse_a2ui_response("Hello")


def test_missing_schema_layout_is_distinct_from_missing_sdk(monkeypatch):
    import importlib
    from praisonaiagents.ui.a2ui import adapter

    def missing_schema(name):
        raise ModuleNotFoundError("No module named a2ui.schema", name="a2ui.schema")

    monkeypatch.setattr(importlib, "import_module", missing_schema)
    with pytest.raises(ImportError, match="legacy schema manager"):
        adapter.get_schema_manager(catalogs=[], accepts_inline_catalogs=True)


def test_schema_transitive_dependency_failure_is_not_misreported(monkeypatch):
    import importlib
    from praisonaiagents.ui.a2ui import adapter

    def missing_dependency(name):
        raise ModuleNotFoundError("No module named unrelated_dependency", name="unrelated_dependency")

    monkeypatch.setattr(importlib, "import_module", missing_dependency)
    with pytest.raises(ImportError) as caught:
        adapter.get_schema_manager()
    assert caught.value.__cause__.name == "unrelated_dependency"
    assert "legacy schema manager" not in str(caught.value)
