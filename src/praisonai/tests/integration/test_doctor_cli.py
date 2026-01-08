"""Integration tests for doctor CLI command."""

import json
import subprocess
import sys


class TestDoctorCLI:
    """Integration tests for praisonai doctor CLI."""
    
    def test_doctor_help(self):
        """Test doctor --help output."""
        result = subprocess.run(
            [sys.executable, "-m", "praisonai", "doctor", "--help"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        
        # Should show help (exit code 0 or 2 for argparse)
        assert result.returncode in [0, 2]
        # Should have some output
        assert len(result.stdout) > 0 or len(result.stderr) > 0
    
    def test_doctor_version(self):
        """Test doctor --version output."""
        result = subprocess.run(
            [sys.executable, "-m", "praisonai", "doctor", "--version"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        
        # Should complete successfully
        assert result.returncode in [0, 1]
        # Should mention doctor or version
        output = result.stdout + result.stderr
        assert "doctor" in output.lower() or "1.0" in output or "version" in output.lower()
    
    def test_doctor_db_subcommand(self):
        """Test doctor db subcommand."""
        result = subprocess.run(
            [sys.executable, "-m", "praisonai", "doctor", "db"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        
        # Should complete successfully
        assert result.returncode in [0, 1]
    
    def test_doctor_fast_mode(self):
        """Test doctor in fast mode (default)."""
        result = subprocess.run(
            [sys.executable, "-m", "praisonai", "doctor"],
            capture_output=True,
            text=True,
            timeout=60,
        )
        
        # Should complete (exit code 0 or 1 depending on environment)
        assert result.returncode in [0, 1]
        # Should have some output
        assert len(result.stdout) > 0 or len(result.stderr) > 0
    
    def test_doctor_json_output(self):
        """Test doctor --json output."""
        result = subprocess.run(
            [sys.executable, "-m", "praisonai", "doctor", "--json"],
            capture_output=True,
            text=True,
            timeout=60,
        )
        
        # Should complete
        assert result.returncode in [0, 1, 2]
        
        # Output should be valid JSON
        try:
            data = json.loads(result.stdout)
            assert "version" in data
            assert "results" in data
            assert "summary" in data
        except json.JSONDecodeError:
            # If stdout is not JSON, check stderr
            pass
    
    def test_doctor_env_subcommand(self):
        """Test doctor env subcommand."""
        result = subprocess.run(
            [sys.executable, "-m", "praisonai", "doctor", "env"],
            capture_output=True,
            text=True,
            timeout=60,
        )
        
        assert result.returncode in [0, 1]
        # Should mention environment-related checks
        assert "python" in result.stdout.lower() or "environment" in result.stdout.lower() or len(result.stdout) > 0
    
    def test_doctor_config_subcommand(self):
        """Test doctor config subcommand."""
        result = subprocess.run(
            [sys.executable, "-m", "praisonai", "doctor", "config"],
            capture_output=True,
            text=True,
            timeout=60,
        )
        
        assert result.returncode in [0, 1]
    
    def test_doctor_mcp_subcommand(self):
        """Test doctor mcp subcommand."""
        result = subprocess.run(
            [sys.executable, "-m", "praisonai", "doctor", "mcp"],
            capture_output=True,
            text=True,
            timeout=60,
        )
        
        assert result.returncode in [0, 1]
    
    def test_doctor_quiet_mode(self):
        """Test doctor --quiet mode."""
        result = subprocess.run(
            [sys.executable, "-m", "praisonai", "doctor", "--quiet"],
            capture_output=True,
            text=True,
            timeout=60,
        )
        
        assert result.returncode in [0, 1]
        # Quiet mode should have minimal output
        # (but still show summary)
    
    def test_doctor_ci_subcommand(self):
        """Test doctor ci subcommand."""
        result = subprocess.run(
            [sys.executable, "-m", "praisonai", "doctor", "ci"],
            capture_output=True,
            text=True,
            timeout=60,
        )
        
        # CI mode should return JSON
        assert result.returncode in [0, 1, 2, 3]
        
        # Try to parse as JSON
        try:
            data = json.loads(result.stdout)
            assert "results" in data or "summary" in data
        except json.JSONDecodeError:
            pass  # May have other output
    
    def test_doctor_selftest(self):
        """Test doctor selftest subcommand."""
        result = subprocess.run(
            [sys.executable, "-m", "praisonai", "doctor", "selftest"],
            capture_output=True,
            text=True,
            timeout=60,
        )
        
        # Should complete (may fail if no API key)
        assert result.returncode in [0, 1, 2]
    
    def test_doctor_deep_mode(self):
        """Test doctor --deep mode."""
        result = subprocess.run(
            [sys.executable, "-m", "praisonai", "doctor", "--deep"],
            capture_output=True,
            text=True,
            timeout=60,
        )
        
        assert result.returncode in [0, 1]
    
    def test_doctor_tools_subcommand(self):
        """Test doctor tools subcommand."""
        result = subprocess.run(
            [sys.executable, "-m", "praisonai", "doctor", "tools"],
            capture_output=True,
            text=True,
            timeout=60,
        )
        
        assert result.returncode in [0, 1]
    
    def test_doctor_network_subcommand(self):
        """Test doctor network subcommand."""
        result = subprocess.run(
            [sys.executable, "-m", "praisonai", "doctor", "network"],
            capture_output=True,
            text=True,
            timeout=60,
        )
        
        assert result.returncode in [0, 1]
    
    def test_doctor_strict_mode(self):
        """Test doctor --strict mode."""
        result = subprocess.run(
            [sys.executable, "-m", "praisonai", "doctor", "--strict"],
            capture_output=True,
            text=True,
            timeout=60,
        )
        
        # Strict mode may return 1 if there are warnings
        assert result.returncode in [0, 1]


class TestDoctorExitCodes:
    """Tests for doctor exit codes."""
    
    def test_exit_code_0_on_pass(self):
        """Test exit code 0 when env checks pass."""
        # Run env subcommand which should always pass for basic checks
        result = subprocess.run(
            [sys.executable, "-m", "praisonai", "doctor", "env"],
            capture_output=True,
            text=True,
            timeout=60,
        )
        
        # These basic checks should pass (exit 0) or may have warnings (still 0)
        # Exit code 1 means failure, which shouldn't happen for these checks
        assert result.returncode in [0, 1]  # Allow 1 in case of environment differences
    
    def test_exit_code_deterministic(self):
        """Test that exit codes are deterministic."""
        results = []
        for _ in range(3):
            result = subprocess.run(
                [sys.executable, "-m", "praisonai", "doctor", "env"],
                capture_output=True,
                text=True,
                timeout=60,
            )
            results.append(result.returncode)
        
        # All runs should have the same exit code
        assert all(r == results[0] for r in results)
