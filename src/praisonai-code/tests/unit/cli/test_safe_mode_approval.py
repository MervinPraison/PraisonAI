"""Regression tests for #6020: `praisonai code --safe` must not pre-approve edits.

Safe mode (the default) writes ``PRAISON_APPROVAL_MODE=prompt``. The tool
loader used to drop that unknown value, keep its permissive ``auto`` default
and register ``edit_file``/``apply_patch`` as standing approvals.
"""

import contextvars
import json
import logging

import pytest

from praisonai_code.cli.features.interactive_tools import (
    ToolConfig,
    get_interactive_tools,
)

try:
    import praisonaiagents.tools.edit_tools  # noqa: F401
    from praisonaiagents.approval import get_approval_registry
except ImportError:  # pragma: no cover
    pytest.skip("praisonaiagents edit tools not available", allow_module_level=True)

EDIT_TOOLS = ("edit_file", "apply_patch")


def _in_fresh_context(fn):
    """Approvals are context-local; start each scenario from an empty context."""
    return contextvars.Context().run(fn)


def _yaml_grants(groups, workspace):
    def run():
        get_interactive_tools(groups=groups, workspace=str(workspace))
        reg = get_approval_registry()
        return {name: reg.is_yaml_approved(name) for name in EDIT_TOOLS}

    return _in_fresh_context(run)


@pytest.mark.parametrize("value", ["prompt", "PROMPT", "bogus"])
def test_safe_and_unknown_modes_are_not_auto(monkeypatch, value):
    monkeypatch.setenv("PRAISON_APPROVAL_MODE", value)
    assert ToolConfig.from_env().approval_mode == "prompt"


def test_unknown_mode_logs_warning(monkeypatch, caplog):
    monkeypatch.setenv("PRAISON_APPROVAL_MODE", "bogus")
    with caplog.at_level(logging.WARNING):
        ToolConfig.from_env()
    assert "Unknown PRAISON_APPROVAL_MODE" in caplog.text


@pytest.mark.parametrize("value", ["auto", "manual", "scoped"])
def test_known_modes_are_kept(monkeypatch, value):
    monkeypatch.setenv("PRAISON_APPROVAL_MODE", value)
    assert ToolConfig.from_env().approval_mode == value


def test_safe_mode_issues_no_edit_grant(monkeypatch, tmp_path):
    monkeypatch.setenv("PRAISON_APPROVAL_MODE", "prompt")
    grants = _yaml_grants(["acp", "edit", "search", "lsp", "mcp"], tmp_path)
    assert grants == {"edit_file": False, "apply_patch": False}


def test_explicit_auto_still_grants(monkeypatch, tmp_path):
    monkeypatch.setenv("PRAISON_APPROVAL_MODE", "auto")
    grants = _yaml_grants(["edit"], tmp_path)
    assert grants == {"edit_file": True, "apply_patch": True}


def test_no_edit_group_no_grant(monkeypatch, tmp_path):
    monkeypatch.setenv("PRAISON_APPROVAL_MODE", "auto")
    grants = _yaml_grants(["basic", "acp", "lsp", "mcp"], tmp_path)
    assert grants == {"edit_file": False, "apply_patch": False}


def test_safe_mode_keeps_acp_orchestrator_approving(monkeypatch, tmp_path):
    """ACP writes must not regress to "Plan is not approved" in safe mode;
    the core per-tool approval gate is the single approval point."""
    from praisonai_code.cli.features.interactive_tools import (
        _get_shared_runtime,
    )

    monkeypatch.setenv("PRAISON_APPROVAL_MODE", "prompt")

    def run():
        config = ToolConfig.from_env()
        config.workspace = str(tmp_path)
        runtime, _ = _get_shared_runtime(config)
        return runtime.config.approval_mode

    assert _in_fresh_context(run) == "auto"


@pytest.mark.parametrize("tool_name,args", [
    ("edit_file", {"filepath": "app.py", "old_string": "DEBUG = False",
                   "new_string": "DEBUG = True", "force": True}),
    ("acp_create_file", {"filepath": "app.py", "content": "DEBUG = True\n"}),
])
def test_safe_mode_edit_reaches_approval_backend(monkeypatch, tmp_path, tool_name, args):
    """End to end: a deny-all backend is consulted and the file is untouched,
    for both the edit tools and the ACP write tools."""
    litellm = pytest.importorskip("litellm")
    from praisonaiagents import Agent
    from praisonaiagents.approval.protocols import ApprovalDecision

    monkeypatch.setenv("PRAISON_APPROVAL_MODE", "prompt")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.delenv("PRAISONAI_TOOL_SAFETY", raising=False)
    monkeypatch.delenv("PRAISONAI_AUTO_APPROVE", raising=False)

    target = tmp_path / "app.py"
    target.write_text("DEBUG = False\n")

    asked = []

    class DenyAll:
        def request_approval_sync(self, request, timeout=None):
            asked.append(request.tool_name)
            return ApprovalDecision(approved=False, reason="denied by test backend")

        async def request_approval(self, request):
            return self.request_approval_sync(request)

    calls = {"n": 0}

    def fake_completion(**kw):
        calls["n"] += 1
        if calls["n"] == 1:
            return litellm.ModelResponse(
                choices=[{"finish_reason": "tool_calls", "message": {
                    "role": "assistant", "content": "", "tool_calls": [{
                        "id": "c1", "type": "function", "function": {
                            "name": tool_name, "arguments": json.dumps(args)}}]}}],
                usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            )
        return litellm.ModelResponse(
            choices=[{"finish_reason": "stop",
                      "message": {"role": "assistant", "content": "done"}}],
            usage={"prompt_tokens": 10, "completion_tokens": 1, "total_tokens": 11},
        )

    monkeypatch.setattr(litellm, "completion", fake_completion)

    registry = get_approval_registry()
    previous = getattr(registry, "_global_backend", None)
    registry.set_backend(DenyAll())
    try:
        def run():
            tools = get_interactive_tools(
                groups=["acp", "edit", "search", "lsp", "mcp"], workspace=str(tmp_path)
            )
            agent = Agent(
                name="coder", instructions="edit",
                model="anthropic/claude-3-5-sonnet-20240620",
                tools=tools, output="silent",
            )
            agent.start("flip DEBUG")

        _in_fresh_context(run)
    finally:
        registry.set_backend(previous)

    assert tool_name in asked
    assert target.read_text() == "DEBUG = False\n"


def test_gemini_backend_default_has_no_bypass(monkeypatch):
    from praisonai_code.cli_backends.gemini import DEFAULT_CONFIG, GeminiBackend

    monkeypatch.delenv("PRAISONAI_GEMINI_BYPASS_PERMISSIONS", raising=False)
    for args in (DEFAULT_CONFIG.args, GeminiBackend().config.args,
                 GeminiBackend(unsafe=True).config.args):
        assert "--yolo" not in args
        assert "--skip-trust" not in args


def test_gemini_backend_bypass_needs_flag_and_env(monkeypatch):
    from praisonai_code.cli_backends.gemini import GeminiBackend

    monkeypatch.setenv("PRAISONAI_GEMINI_BYPASS_PERMISSIONS", "1")
    assert "--yolo" not in GeminiBackend().config.args
    args = GeminiBackend(unsafe=True).config.args
    assert "--yolo" in args and "--skip-trust" in args
