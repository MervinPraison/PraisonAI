"""Real agentic test: --external-agent uses manager Agent delegation by default."""
import os
import shutil
import subprocess
import pytest


@pytest.mark.skipif(not shutil.which("claude"), reason="claude CLI not installed")
@pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="OPENAI_API_KEY required for manager LLM")
def test_external_agent_manager_delegation_default():
    """Real agentic test: default --external-agent uses manager Agent + subagent tool."""
    result = subprocess.run(
        ["praisonai", "Say hi in exactly 5 words", "--external-agent", "claude"],
        capture_output=True, text=True, timeout=120,
    )
    assert result.returncode == 0
    assert "manager delegation" in result.stdout.lower()
    assert len(result.stdout.strip()) > 0


@pytest.mark.skipif(not shutil.which("claude"), reason="claude CLI not installed")
def test_external_agent_direct_flag_preserves_proxy():
    """Escape hatch: --external-agent-direct preserves pass-through proxy."""
    result = subprocess.run(
        ["praisonai", "Say hi in exactly 5 words", "--external-agent", "claude",
         "--external-agent-direct"],
        capture_output=True, text=True, timeout=120,
    )
    assert result.returncode == 0
    assert "direct" in result.stdout.lower()
    assert len(result.stdout.strip()) > 0