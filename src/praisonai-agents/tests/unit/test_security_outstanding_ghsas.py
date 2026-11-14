"""Tests for outstanding GHSA security fixes in praisonaiagents."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest


def test_searxng_url_blocks_private_ip():
    from praisonaiagents.tools.url_safety import validate_searxng_url

    assert validate_searxng_url("http://10.0.0.1/search") is None


def test_workflow_yaml_approve_gated_without_allow_dangerous(monkeypatch):
    """GHSA-7qw2: approve list must not auto-approve when allow_dangerous_tools=False."""
    from praisonaiagents import Workflow
    from praisonaiagents.approval import (
        get_approval_registry, reset_yaml_approved_tools, set_yaml_approved_tools,
    )
    from praisonaiagents.workflows.workflow_configs import WorkflowHooksConfig

    def no_network(*args, **kwargs):
        pytest.fail("unexpected network connection")

    monkeypatch.setattr("socket.socket.connect", no_network)
    monkeypatch.setattr("socket.socket.connect_ex", no_network)
    registry = get_approval_registry()
    token = set_yaml_approved_tools([])
    try:
        for allowed in (False, True):
            observed = []
            wf = Workflow(steps=[], hooks=WorkflowHooksConfig(
                on_workflow_start=lambda *_: observed.append(
                    set(registry._yaml_approved_tools.get() or ())
                )
            ))
            wf.approve_tools = ["execute_command"]
            wf.allow_dangerous_tools = allowed
            wf.run("hello", verbose=False)
            assert observed == [{"execute_command"} if allowed else set()]
            assert not registry._yaml_approved_tools.get()
    finally:
        reset_yaml_approved_tools(token)


def test_search_tools_read_file_blocks_traversal(tmp_path):
    """GHSA-4xxv: read_file must stay within workspace."""
    from praisonaiagents.context.fast.search_tools import read_file

    outside = tmp_path / "secret.txt"
    outside.write_text("secret")
    ws = tmp_path / "ws"
    ws.mkdir()
    result = read_file(str(outside), workspace_root=str(ws))
    assert result["success"] is False
    assert "outside workspace" in result["error"].lower()


def test_memory_output_file_contained(tmp_path, monkeypatch):
    """GHSA-qjw5: auto-save output must stay in project root."""
    from praisonaiagents.agent.memory_mixin import MemoryMixin

    class _Agent(MemoryMixin):
        def __init__(self):
            self._output_file = str(tmp_path.parent / "outside.txt")
            self.name = "t"

    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("PRAISONAI_PROJECT_ROOT", raising=False)
    agent = _Agent()
    assert agent._save_output_to_file("data") is False


def test_skill_tools_blocks_outside_script(tmp_path, monkeypatch):
    """GHSA-c44f: skill script path must stay in working directory."""
    from praisonaiagents.tools.skill_tools import SkillTools

    monkeypatch.setenv("PRAISONAI_AUTO_APPROVE", "true")
    outside = tmp_path / "evil.py"
    outside.write_text("print('x')")
    tools = SkillTools(working_directory=str(tmp_path / "ws"))
    (tmp_path / "ws").mkdir()
    result = tools.run_skill_script(str(outside))
    assert "outside working directory" in result.lower()


def test_web_crawl_blocks_private_ip(monkeypatch):
    """GHSA-qg25: web_crawl SSRF blocks private targets."""
    from praisonaiagents.tools import web_crawl_tools

    monkeypatch.delenv("ALLOW_LOCAL_CRAWL", raising=False)
    monkeypatch.setattr(
        "socket.getaddrinfo",
        lambda *args, **kwargs: [(2, 1, 6, "", ("169.254.169.254", 0))],
    )
    monkeypatch.setattr(
        web_crawl_tools, "_get_available_crawl_providers",
        lambda: pytest.fail("unsafe URL reached provider discovery"),
    )
    result = web_crawl_tools.web_crawl("http://169.254.169.254/latest/meta-data/")
    assert "error" in result


def test_approval_cache_varies_by_arguments():
    """GHSA-29r9: approval cache must include tool arguments."""
    from praisonaiagents.approval.registry import ApprovalRegistry

    registry = ApprovalRegistry()
    registry.mark_approved("run", {"cmd": "ls"})
    assert registry.is_already_approved("run", {"cmd": "ls"})
    assert not registry.is_already_approved("run", {"cmd": "rm -rf /"})


def test_workflow_tools_py_gated(monkeypatch, tmp_path):
    """GHSA-4gfv: tools.py loading requires PRAISONAI_ALLOW_LOCAL_TOOLS."""
    from praisonaiagents.workflows.workflows import Workflow

    wf_dir = tmp_path / "wf"
    wf_dir.mkdir()
    (wf_dir / "tools.py").write_text(
        "from pydantic import BaseModel\nclass Out(BaseModel):\n    x: int\n"
    )
    wf = Workflow(steps=[], file_path=str(wf_dir / "flow.yaml"))
    monkeypatch.delenv("PRAISONAI_ALLOW_LOCAL_TOOLS", raising=False)
    assert wf._resolve_pydantic_class("Out") is None

    monkeypatch.setenv("PRAISONAI_ALLOW_LOCAL_TOOLS", "true")
    cls = wf._resolve_pydantic_class("Out")
    assert cls is not None


def test_plugin_discovery_opt_in(monkeypatch):
    """GHSA-m6wp: plugin auto-discovery is opt-in."""
    from praisonaiagents.plugins.manager import PluginManager

    monkeypatch.delenv("PRAISONAI_ALLOW_PLUGIN_DISCOVERY", raising=False)
    manager = PluginManager()
    assert manager.auto_discover_plugins() == 0

