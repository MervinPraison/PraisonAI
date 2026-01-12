"""
Advanced Agent-Centric Test Scenarios.

These scenarios test the agent's ability to AUTONOMOUSLY complete complex tasks
using ONLY a single text prompt. The agent must figure out the approach itself.

Key Principles:
- ONE prompt per scenario (no step-by-step instructions)
- Prompt describes WHAT to achieve, not HOW
- Agent uses tools autonomously to complete the task
- Verification checks the END RESULT, not the process
"""

import os


def is_advanced_tests_enabled() -> bool:
    """Check if advanced tests are enabled."""
    return os.environ.get("PRAISONAI_LIVE_INTERACTIVE", "0") == "1"


def has_api_key() -> bool:
    """Check if API key is available."""
    return bool(os.environ.get("OPENAI_API_KEY"))


def can_run_advanced_tests() -> tuple:
    """Check if advanced tests can run."""
    if not is_advanced_tests_enabled():
        return False, "PRAISONAI_LIVE_INTERACTIVE=1 not set"
    if not has_api_key():
        return False, "OPENAI_API_KEY not set"
    return True, "OK"


__all__ = [
    "is_advanced_tests_enabled",
    "has_api_key", 
    "can_run_advanced_tests",
]
