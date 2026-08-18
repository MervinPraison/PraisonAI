"""Tests for issue #4024 — entrypoint-independent first-run onboarding.

The credential onboarding gate (detect provider keys → offer the `setup` wizard
when none are configured, or adopt a keyless local endpoint) used to be wired
only into the bare ``praisonai`` invocation and ``praisonai run``. A keyless
newcomer whose first command was ``praisonai code "…"`` / ``praisonai chat "…"``
never reached onboarding and dead-ended on a raw provider error.

The fix extracts the gate into a single shared helper
``ensure_configured_or_onboard`` (in ``praisonai_code.llm.credentials``) that
``code``, ``chat``, ``run``, and the bare invocation all pass through. These
tests exercise the helper's behaviour directly, which is what each entrypoint
now delegates to.
"""

import pytest
import typer

from praisonai_code.llm import credentials as creds


_PROVIDER_KEY_VARS = (
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "GEMINI_API_KEY",
    "GOOGLE_API_KEY",
    "GROQ_API_KEY",
    "COHERE_API_KEY",
    "OPENROUTER_API_KEY",
    "OLLAMA_HOST",
)


@pytest.fixture
def clean_env(monkeypatch):
    for var in _PROVIDER_KEY_VARS + ("OPENAI_BASE_URL", "MODEL_NAME", "OPENAI_MODEL_NAME"):
        monkeypatch.delenv(var, raising=False)
    return monkeypatch


def test_helper_exists_and_is_the_shared_choke_point():
    # The entrypoints (code/chat/run/app) all import this one helper.
    assert hasattr(creds, "ensure_configured_or_onboard")


def test_configured_returns_model_unchanged(clean_env, monkeypatch):
    monkeypatch.setattr(creds, "inject_credentials_into_env", lambda: False)
    monkeypatch.setattr(creds, "is_configured", lambda model=None: True)

    def _boom(*a, **k):
        raise AssertionError("local detection consulted while configured")

    monkeypatch.setattr(creds, "detect_local_endpoint", _boom)

    assert creds.ensure_configured_or_onboard(model="gpt-4o", interactive=True) == "gpt-4o"


def test_headless_keyless_exits_nonzero_with_setup_hint(clean_env, monkeypatch, capsys):
    monkeypatch.setattr(creds, "inject_credentials_into_env", lambda: False)
    monkeypatch.setattr(creds, "is_configured", lambda model=None: False)
    monkeypatch.setattr(creds, "detect_local_endpoint", lambda: None)

    with pytest.raises(typer.Exit) as exc:
        creds.ensure_configured_or_onboard(model=None, interactive=False)

    assert exc.value.exit_code == 1
    err = capsys.readouterr().err
    assert "praisonai setup" in err


def test_headless_does_not_prompt(clean_env, monkeypatch):
    monkeypatch.setattr(creds, "inject_credentials_into_env", lambda: False)
    monkeypatch.setattr(creds, "is_configured", lambda model=None: False)
    monkeypatch.setattr(creds, "detect_local_endpoint", lambda: None)

    def _no_confirm(*a, **k):
        raise AssertionError("headless path must never prompt")

    monkeypatch.setattr(typer, "confirm", _no_confirm)

    with pytest.raises(typer.Exit):
        creds.ensure_configured_or_onboard(model="gpt-4o", interactive=False)


def test_keyless_local_first_adopts_local_model(clean_env, monkeypatch):
    from praisonai_code.llm.local_detect import LocalModel

    monkeypatch.setattr(creds, "inject_credentials_into_env", lambda: False)
    monkeypatch.setattr(creds, "is_configured", lambda model=None: False)
    monkeypatch.setattr(
        creds,
        "detect_local_endpoint",
        lambda: LocalModel(model="ollama/llama3.2", base_url="http://127.0.0.1:11434/v1"),
    )

    result = creds.ensure_configured_or_onboard(model=None, interactive=True)
    assert result == "ollama/llama3.2"

    import os

    assert os.environ.get("OPENAI_BASE_URL") == "http://127.0.0.1:11434/v1"


def test_explicit_model_skips_local_first(clean_env, monkeypatch):
    # An explicit --model disables the keyless local-first fallback (its own
    # provider gate applies), so detection must not even be consulted.
    monkeypatch.setattr(creds, "inject_credentials_into_env", lambda: False)
    monkeypatch.setattr(creds, "is_configured", lambda model=None: False)

    def _boom():
        raise AssertionError("local detection consulted despite explicit model")

    monkeypatch.setattr(creds, "detect_local_endpoint", _boom)

    with pytest.raises(typer.Exit):
        creds.ensure_configured_or_onboard(model="gpt-4o", interactive=False)


def test_interactive_declining_wizard_exits_zero(clean_env, monkeypatch, capsys):
    monkeypatch.setattr(creds, "inject_credentials_into_env", lambda: False)
    monkeypatch.setattr(creds, "is_configured", lambda model=None: False)
    monkeypatch.setattr(creds, "detect_local_endpoint", lambda: None)
    monkeypatch.setattr(typer, "confirm", lambda *a, **k: False)

    with pytest.raises(typer.Exit) as exc:
        creds.ensure_configured_or_onboard(model=None, interactive=True)

    assert exc.value.exit_code == 0
    out = capsys.readouterr().out
    assert "praisonai setup" in out


def test_interactive_accepting_wizard_runs_setup_and_rechecks(clean_env, monkeypatch):
    calls = {"n": 0}

    def _is_configured(model=None):
        # Unconfigured first, configured after the wizard runs.
        return calls["n"] > 0

    monkeypatch.setattr(creds, "inject_credentials_into_env", lambda: False)
    monkeypatch.setattr(creds, "is_configured", _is_configured)
    monkeypatch.setattr(creds, "detect_local_endpoint", lambda: None)
    monkeypatch.setattr(typer, "confirm", lambda *a, **k: True)

    import praisonai_code.cli.commands.setup as setup_mod

    def _fake_setup(**kwargs):
        calls["n"] += 1
        return 0

    monkeypatch.setattr(setup_mod, "_run_setup", _fake_setup)

    result = creds.ensure_configured_or_onboard(model=None, interactive=True)
    assert calls["n"] == 1
    assert result is None


def test_interactive_failed_setup_exits_nonzero(clean_env, monkeypatch):
    monkeypatch.setattr(creds, "inject_credentials_into_env", lambda: False)
    monkeypatch.setattr(creds, "is_configured", lambda model=None: False)
    monkeypatch.setattr(creds, "detect_local_endpoint", lambda: None)
    monkeypatch.setattr(typer, "confirm", lambda *a, **k: True)

    import praisonai_code.cli.commands.setup as setup_mod

    monkeypatch.setattr(setup_mod, "_run_setup", lambda **k: 2)

    with pytest.raises(typer.Exit) as exc:
        creds.ensure_configured_or_onboard(model=None, interactive=True)
    assert exc.value.exit_code == 2


def test_code_command_invokes_shared_gate(clean_env, monkeypatch):
    # Regression: `praisonai code` must reach the shared onboarding gate. Prove
    # the wiring by asserting code_main calls ensure_configured_or_onboard and
    # aborts (headless keyless) instead of constructing an Agent.
    from praisonai_code.cli.commands import code as code_mod

    seen = {"called": False}

    def _gate(*, model=None, interactive=True):
        seen["called"] = True
        raise typer.Exit(1)

    monkeypatch.setattr(creds, "ensure_configured_or_onboard", _gate)

    with pytest.raises(typer.Exit):
        code_mod.code_main(
            ctx=None,
            prompt="hello",
            model=None,
            verbose=False,
            tools=None,
            workspace=None,
            file=None,
            no_acp=False,
            no_lsp=False,
            safe_mode=True,
            plan=False,
            dangerously_skip_approval=False,
            checkpoints=False,
            revert=None,
            session_id=None,
            resume=None,
            continue_session=False,
            agent=None,
            thinking=None,
            autonomy=True,
            append_system_prompt=None,
            profile=False,
            profile_deep=False,
            print_mode=True,
            output="json",
            pure=False,
        )

    assert seen["called"] is True


def test_code_gate_receives_profile_model_not_none(clean_env, monkeypatch):
    # Regression (greptile P1): `code --agent <profile>` (no --model) must pass
    # the profile's llm to the gate, so onboarding validates/preserves the model
    # the session actually dispatches instead of silently adopting a keyless
    # local model. The gate would otherwise be handed ``None`` and could return
    # a detected local model, shadowing the profile.
    from praisonai_code.cli.commands import code as code_mod
    from praisonai_code.cli.features import custom_definitions as cd_mod

    monkeypatch.setattr(
        cd_mod, "load_agent_from_name", lambda name: {"llm": "anthropic/claude-3-5-sonnet"}
    )

    seen = {"model": "unset"}

    def _gate(*, model=None, interactive=True):
        seen["model"] = model
        raise typer.Exit(0)

    monkeypatch.setattr(creds, "ensure_configured_or_onboard", _gate)

    with pytest.raises(typer.Exit):
        code_mod.code_main(
            ctx=None,
            prompt=None,
            model=None,
            verbose=False,
            tools=None,
            workspace=None,
            file=None,
            no_acp=False,
            no_lsp=False,
            safe_mode=True,
            plan=False,
            dangerously_skip_approval=False,
            checkpoints=False,
            revert=None,
            session_id=None,
            resume=None,
            continue_session=False,
            agent="reviewer",
            thinking=None,
            autonomy=True,
            append_system_prompt=None,
            profile=False,
            profile_deep=False,
            print_mode=False,
            output=None,
            pure=False,
        )

    assert seen["model"] == "anthropic/claude-3-5-sonnet"


def test_chat_gate_receives_resolved_model(clean_env, monkeypatch):
    # Regression (greptile P1): `chat` (no --model) must resolve the model the
    # TUI will dispatch (e.g. the most-recently-used model) BEFORE the gate, so
    # onboarding validates that exact model rather than passing on any present
    # key for a different provider.
    from praisonai_code.cli.commands import chat as chat_mod
    from praisonai_code.cli.configuration import model_resolver as mr_mod

    monkeypatch.setattr(
        mr_mod, "resolve_default_model", lambda explicit=None: "gemini/gemini-1.5-pro"
    )

    # The interactive (no-prompt) path only gates once the wrapper-resident TUI
    # can start; force it available so this test exercises the gate rather than
    # the standalone install-hint short-circuit (see chat_main).
    import praisonai_code._wrapper_bridge as _bridge

    monkeypatch.setattr(_bridge, "wrapper_available", lambda: True)

    seen = {"model": "unset"}

    def _gate(*, model=None, interactive=True):
        seen["model"] = model
        raise typer.Exit(0)

    monkeypatch.setattr(creds, "ensure_configured_or_onboard", _gate)

    with pytest.raises(typer.Exit):
        chat_mod.chat_main(
            ctx=None,
            prompt=None,
            model=None,
            verbose=False,
            memory=None,
            no_memory=False,
            tools=None,
            toolset=None,
            user_id=None,
            session_id=None,
            continue_session=False,
            file=None,
            workspace=None,
            no_acp=False,
            no_lsp=False,
            safe_mode=False,
            autonomy=True,
            append_system_prompt=None,
            knowledge=None,
            guardrails=None,
            web=None,
            reflection=None,
            planning=None,
            context=None,
            output=None,
            execution=None,
            hooks=None,
            caching=None,
            approval=None,
            profile=False,
            profile_deep=False,
            debug=False,
            ui_backend="auto",
            json_output=True,
            no_color=False,
            theme="default",
            compact=False,
            no_rules=False,
            pure=False,
        )

    assert seen["model"] == "gemini/gemini-1.5-pro"


def test_chat_interactive_standalone_skips_gate_for_install_hint(clean_env, monkeypatch):
    # Regression (smoke): keyless interactive `chat` on a standalone
    # `pip install praisonai-code` (no wrapper) must NOT be preempted by the
    # onboarding gate. The wrapper-resident TUI surfaces its own actionable
    # install hint (`pip install praisonai[tui]`); running the credential gate
    # first would dead-end a newcomer with "No API key configured" for a session
    # that cannot even start. The gate is skipped when the wrapper is absent and
    # no prompt was given.
    from praisonai_code.cli.commands import chat as chat_mod
    from praisonai_code.cli.configuration import model_resolver as mr_mod
    import praisonai_code._wrapper_bridge as _bridge

    monkeypatch.setattr(
        mr_mod, "resolve_default_model", lambda explicit=None: "gpt-4o"
    )
    monkeypatch.setattr(_bridge, "wrapper_available", lambda: False)

    def _gate(*, model=None, interactive=True):
        raise AssertionError("gate must not run for standalone interactive chat")

    monkeypatch.setattr(creds, "ensure_configured_or_onboard", _gate)

    launched = {"tui": False}

    class _StubTUI:
        def __init__(self, *a, **k):
            pass

        def run(self):
            launched["tui"] = True

    monkeypatch.setattr(
        "praisonai_code.cli.interactive.async_tui.AsyncTUI", _StubTUI
    )

    chat_mod.chat_main(
        ctx=None,
        prompt=None,
        model=None,
        verbose=False,
        memory=None,
        no_memory=False,
        tools=None,
        toolset=None,
        user_id=None,
        session_id=None,
        continue_session=False,
        file=None,
        workspace=None,
        no_acp=False,
        no_lsp=False,
        safe_mode=False,
        autonomy=True,
        append_system_prompt=None,
        knowledge=None,
        guardrails=None,
        web=None,
        reflection=None,
        planning=None,
        context=None,
        output=None,
        execution=None,
        hooks=None,
        caching=None,
        approval=None,
        profile=False,
        profile_deep=False,
        debug=False,
        ui_backend="auto",
        json_output=False,
        no_color=False,
        theme="default",
        compact=False,
        no_rules=False,
        pure=False,
    )

    assert launched["tui"] is True
