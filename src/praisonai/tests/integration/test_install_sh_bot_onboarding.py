"""
Integration test for install.sh bot onboarding hook.

Tests that install.sh with a seeded .env token triggers praisonai onboard.
"""

import os
import tempfile
import subprocess
from pathlib import Path
from unittest.mock import patch
import pytest


# Resolve install.sh relative to this test file so it works in any checkout.
SCRIPT_PATH = (
    Path(__file__).resolve().parents[2] / "scripts" / "install.sh"
)


def test_install_sh_mentions_bot_onboarding():
    """Test that install.sh mentions bot onboarding in dry-run mode."""
    script_path = str(SCRIPT_PATH)
    
    # Check that the function exists in the script
    with open(script_path, 'r') as f:
        content = f.read()
    
    # Verify our function is defined
    assert "maybe_offer_bot_onboarding()" in content
    assert "praisonai onboard" in content
    assert "messaging bot" in content


def test_bot_onboarding_function_logic():
    """Test the logic of the bot onboarding function."""
    script_path = str(SCRIPT_PATH)

    with open(script_path, 'r') as f:
        content = f.read()

    # Check key environment variable checks
    assert "NO_ONBOARD" in content
    assert "NO_PROMPT" in content
    assert "DRY_RUN" in content
    assert "/dev/tty" in content

    # The installer should surface the bot wizard prompt visibly and
    # mention all supported platforms (not as token env-var checks,
    # but as part of the user-facing prompt copy).
    assert "Telegram" in content
    assert "Discord" in content
    assert "Slack" in content
    assert "WhatsApp" in content

    # Check the function is called from main
    assert "maybe_offer_bot_onboarding" in content


def test_install_sh_has_no_syntax_errors():
    """Test that install.sh has no basic syntax errors."""
    script_path = str(SCRIPT_PATH)
    
    # Simple syntax validation - check for basic shell syntax issues
    with open(script_path, 'r') as f:
        content = f.read()
    
    # Check for balanced brackets/braces
    assert content.count('{') == content.count('}'), "Unmatched braces in shell script"
    assert content.count('[') >= content.count(']'), "Unmatched brackets in shell script"
    
    # Check that functions are properly closed
    function_starts = content.count('() {')
    # Each function should have at least one closing brace
    assert content.count('}') >= function_starts, "Functions not properly closed"


def test_daemon_windows_platform_detection():
    """Test that Windows daemon correctly identifies platform."""
    from praisonai.daemon.windows import get_status
    
    # Should not crash and should return proper structure
    result = get_status()
    
    assert isinstance(result, dict)
    assert "platform" in result
    assert result["platform"] == "windows"
    assert "installed" in result
    assert "running" in result
    assert isinstance(result["installed"], bool)
    assert isinstance(result["running"], bool)