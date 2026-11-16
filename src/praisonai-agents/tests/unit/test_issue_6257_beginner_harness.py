"""Regression tests for issue #6257 (beginner harness demo)."""
from praisonaiagents import Agent
from praisonaiagents.llm.openai_client import OpenAIClient


def test_guardrail_runs_when_agent_has_no_name():
    seen = []

    def check(output):
        seen.append(output.agent)
        return True, output

    agent = Agent(instructions="test", llm="gpt-4o-mini", guardrails=check)
    assert agent.name is None or isinstance(agent.name, str)

    ok, result, error = agent._validate_with_guardrail("hello")

    assert ok is True and error is None
    assert result == "hello"
    assert seen and isinstance(seen[0], str)


def test_openai_timeout_env_var(monkeypatch):
    monkeypatch.setenv("OPENAI_TIMEOUT", "45")
    assert OpenAIClient(api_key="sk-test").timeout == 45.0

    monkeypatch.setenv("OPENAI_TIMEOUT", "not-a-number")
    assert OpenAIClient(api_key="sk-test").timeout is None

    monkeypatch.delenv("OPENAI_TIMEOUT")
    assert OpenAIClient(api_key="sk-test").timeout is None


def test_openai_timeout_reaches_sync_client(monkeypatch):
    monkeypatch.setenv("OPENAI_TIMEOUT", "12")
    client = OpenAIClient(api_key="sk-test")
    monkeypatch.setattr(
        "praisonaiagents.llm.openai_client.check_model_request", lambda *a, **k: None
    )
    assert client.sync_client.timeout == 12.0


def test_rules_notice_lists_only_active_rules_once(tmp_path, monkeypatch, caplog):
    import logging
    from praisonaiagents.agent import agent as agent_mod

    rules_dir = tmp_path / ".praisonai" / "rules"
    rules_dir.mkdir(parents=True)
    (rules_dir / "always_on.md").write_text("---\nactivation: always\n---\nBe brief.\n")
    (rules_dir / "manual_only.md").write_text("---\nactivation: manual\n---\nOnly on @mention.\n")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setattr(agent_mod, "_RULES_NOTICE_SEEN", set())

    with caplog.at_level(logging.WARNING):
        for _ in range(2):
            a = Agent(instructions="test", llm="gpt-4o-mini")
            a._init_rules_manager()

    notices = [r.getMessage() for r in caplog.records if "Applied rules" in r.getMessage()]
    assert len(notices) == 1
    assert "always_on" in notices[0] and "manual_only" not in notices[0]
