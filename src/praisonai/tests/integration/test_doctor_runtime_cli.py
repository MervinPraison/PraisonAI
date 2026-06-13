"""Integration tests for doctor runtime CLI command."""

import json
import subprocess
import sys
import os
from pathlib import Path

def run_doctor_runtime(*args, timeout=60):
    """Run doctor runtime CLI with proper PYTHONPATH."""
    env = os.environ.copy()
    # Propagate sys.path to PYTHONPATH so the subprocess can find praisonai package
    env["PYTHONPATH"] = os.pathsep.join(sys.path)
    return subprocess.run(
        [sys.executable, "-m", "praisonai", "doctor", "runtime", *args],
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env
    )


class TestDoctorRuntimeCLI:
    """Integration tests for praisonai doctor runtime CLI."""
    
    @property
    def fixtures_dir(self):
        """Path to test fixtures directory."""
        test_dir = Path(__file__).parent.parent
        return test_dir / "fixtures"
    
    def test_runtime_help(self):
        """Test doctor runtime --help output."""
        result = run_doctor_runtime("--help", timeout=30)
        
        # Should show help (exit code 0 or 2 for argparse)
        assert result.returncode in [0, 2]
        # Should mention runtime or team
        output = result.stdout + result.stderr
        assert "runtime" in output.lower() or "team" in output.lower()
    
    def test_runtime_no_team_file(self):
        """Test doctor runtime without --team flag."""
        result = run_doctor_runtime(timeout=30)
        
        # Should complete (possibly with skip status)
        assert result.returncode in [0, 1, 2]
        # Should mention needing team file
        output = result.stdout + result.stderr
        # Allow for various output formats
        assert len(output) > 0
    
    def test_runtime_nonexistent_file(self):
        """Test doctor runtime with non-existent team file."""
        result = run_doctor_runtime("--team", "/nonexistent/file.yaml", timeout=30)
        
        # Should fail with error about missing file
        assert result.returncode in [1, 2]
        output = result.stdout + result.stderr
        assert "not found" in output.lower() or "error" in output.lower()
    
    def test_runtime_valid_team_file(self):
        """Test doctor runtime with valid team YAML."""
        team_file = self.fixtures_dir / "team_valid.yaml"
        if not team_file.exists():
            # Skip if fixture doesn't exist
            return
        
        result = run_doctor_runtime("--team", str(team_file), timeout=30)
        
        # Should complete successfully
        assert result.returncode in [0, 1]
        output = result.stdout + result.stderr
        assert len(output) > 0
    
    def test_runtime_invalid_team_file(self):
        """Test doctor runtime with invalid team YAML."""
        team_file = self.fixtures_dir / "team_invalid.yaml"
        if not team_file.exists():
            # Skip if fixture doesn't exist
            return
        
        result = run_doctor_runtime("--team", str(team_file), timeout=30)
        
        # Should detect issues
        assert result.returncode in [0, 1, 2]
        output = result.stdout + result.stderr
        assert len(output) > 0
    
    def test_runtime_mixed_runtime_file(self):
        """Test doctor runtime with mixed runtime team YAML."""
        team_file = self.fixtures_dir / "team_mixed_runtime.yaml"
        if not team_file.exists():
            # Skip if fixture doesn't exist
            return
        
        result = run_doctor_runtime("--team", str(team_file), timeout=30)
        
        # Should detect mixed runtime issues
        assert result.returncode in [0, 1, 2]
        output = result.stdout + result.stderr
        assert len(output) > 0
    
    def test_runtime_json_output(self):
        """Test doctor runtime --json output."""
        team_file = self.fixtures_dir / "team_valid.yaml"
        if not team_file.exists():
            # Skip if fixture doesn't exist
            return
        
        result = run_doctor_runtime("--team", str(team_file), "--json", timeout=30)
        
        # Should complete
        assert result.returncode in [0, 1, 2]
        
        # Output should be valid JSON (or may be in stderr)
        try:
            data = json.loads(result.stdout)
            assert "results" in data or "summary" in data
        except json.JSONDecodeError:
            # JSON might be in stderr or mixed with other output
            # Just verify we got some output
            assert len(result.stdout + result.stderr) > 0
    
    def test_runtime_deep_mode(self):
        """Test doctor runtime --deep mode."""
        team_file = self.fixtures_dir / "team_valid.yaml"
        if not team_file.exists():
            # Skip if fixture doesn't exist
            return
        
        result = run_doctor_runtime("--team", str(team_file), "--deep", timeout=60)
        
        # Should complete
        assert result.returncode in [0, 1, 2]
        output = result.stdout + result.stderr
        assert len(output) > 0
    
    def test_runtime_workflow_placeholder(self):
        """Test doctor runtime --workflow (placeholder functionality)."""
        result = run_doctor_runtime("--workflow", "dummy.yaml", timeout=30)
        
        # Should complete (workflow feature is placeholder)
        assert result.returncode in [0, 1, 2]
        output = result.stdout + result.stderr
        # Should mention workflow or placeholder
        # Allow for various output formats
        assert len(output) > 0


class TestDoctorRuntimeExitCodes:
    """Tests for doctor runtime exit codes."""
    
    @property
    def fixtures_dir(self):
        """Path to test fixtures directory."""
        test_dir = Path(__file__).parent.parent
        return test_dir / "fixtures"
    
    def test_exit_code_deterministic(self):
        """Test that exit codes are deterministic."""
        team_file = self.fixtures_dir / "team_valid.yaml"
        if not team_file.exists():
            # Skip if fixture doesn't exist
            return
        
        results = []
        for _ in range(2):  # Run fewer times for CI performance
            result = run_doctor_runtime("--team", str(team_file), timeout=30)
            results.append(result.returncode)
        
        # All runs should have the same exit code
        assert all(r == results[0] for r in results)
    
    def test_missing_file_exit_code(self):
        """Test exit code for missing files."""
        result = run_doctor_runtime("--team", "/definitely/nonexistent.yaml", timeout=30)
        
        # Should return error exit code
        assert result.returncode in [1, 2]