"""
Integration tests for the setup command.

Tests the end-to-end setup process including file creation,
directory structure, and real command execution.
"""

import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def temp_praison_home():
    """Provide a temporary directory for ~/.praisonai/"""
    with tempfile.TemporaryDirectory() as temp_dir:
        yield Path(temp_dir)


class TestSetupIntegration:
    """Integration tests for the setup command."""

    def test_setup_command_execution(self, temp_praison_home):
        """Test that the setup command can be executed end-to-end."""
        # Set up environment
        env = os.environ.copy()
        env["PRAISONAI_HOME"] = str(temp_praison_home)
        
        # Run setup command in non-interactive mode
        cmd = [
            sys.executable, "-m", "praisonai", "setup",
            "--non-interactive",
            "--provider", "openai",
            "--api-key", "sk-integration-test",
            "--model", "gpt-4o-mini"
        ]
        
        result = subprocess.run(
            cmd,
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
            cwd=PROJECT_ROOT,
        )
        
        # Check command succeeded
        assert result.returncode == 0, f"Command failed: {result.stderr}"
        assert "Setup complete" in result.stdout
        
        # Verify file structure was created
        assert (temp_praison_home / ".env").exists()
        assert (temp_praison_home / "logs").is_dir()
        assert (temp_praison_home / "sessions").is_dir()
        
        # Verify .env content
        env_content = (temp_praison_home / ".env").read_text()
        assert "OPENAI_API_KEY=sk-integration-test" in env_content

    def test_setup_help_output(self):
        """Test that setup --help works."""
        cmd = [sys.executable, "-m", "praisonai", "setup", "--help"]
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=10,
            cwd=PROJECT_ROOT,
        )
        
        assert result.returncode == 0
        assert "Interactive onboarding" in result.stdout or "configuration wizard" in result.stdout

    def test_setup_creates_directories_with_correct_permissions(self, temp_praison_home):
        """Test that setup creates directories with correct permissions."""
        env = os.environ.copy()
        env["PRAISONAI_HOME"] = str(temp_praison_home)
        
        cmd = [
            sys.executable, "-m", "praisonai", "setup",
            "--non-interactive",
            "--provider", "ollama",
            "--model", "llama3.2"
        ]
        
        result = subprocess.run(
            cmd,
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
            cwd=PROJECT_ROOT,
        )
        
        assert result.returncode == 0
        
        # Check directory permissions
        logs_dir = temp_praison_home / "logs"
        sessions_dir = temp_praison_home / "sessions"
        
        assert logs_dir.is_dir()
        assert sessions_dir.is_dir()
        
        # Directories should be readable/writable/executable by owner
        logs_mode = oct(logs_dir.stat().st_mode)[-3:]
        sessions_mode = oct(sessions_dir.stat().st_mode)[-3:]
        
        # Should be 700 or 755 (depends on umask)
        assert logs_mode in ["700", "755"]
        assert sessions_mode in ["700", "755"]

    def test_setup_idempotency_integration(self, temp_praison_home):
        """Test that running setup multiple times doesn't break anything."""
        env = os.environ.copy()
        env["PRAISONAI_HOME"] = str(temp_praison_home)
        
        base_cmd = [
            sys.executable, "-m", "praisonai", "setup",
            "--non-interactive",
            "--provider", "openai",
            "--model", "gpt-4o-mini"
        ]
        
        # First run
        cmd1 = base_cmd + ["--api-key", "sk-first-run"]
        result1 = subprocess.run(
            cmd1,
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
            cwd=PROJECT_ROOT,
        )
        assert result1.returncode == 0
        
        # Second run with different key
        cmd2 = base_cmd + ["--api-key", "sk-second-run"]
        result2 = subprocess.run(
            cmd2,
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
            cwd=PROJECT_ROOT,
        )
        assert result2.returncode == 0
        
        # Verify final state
        env_content = (temp_praison_home / ".env").read_text()
        assert "OPENAI_API_KEY=sk-second-run" in env_content
        assert "sk-first-run" not in env_content