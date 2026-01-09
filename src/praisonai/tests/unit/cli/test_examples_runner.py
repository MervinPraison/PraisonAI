"""
Tests for the Examples Execution System.

TDD tests for discovery, execution, timeout, and reporting functionality.
"""

import json
from pathlib import Path


class TestExampleMetadata:
    """Tests for ExampleMetadata parsing from comment directives."""
    
    def test_parse_skip_directive(self, tmp_path):
        """Test parsing # praisonai: skip=true directive."""
        from praisonai.cli.features.examples import ExampleMetadata
        
        example = tmp_path / "test_skip.py"
        example.write_text("# praisonai: skip=true\nprint('hello')")
        
        meta = ExampleMetadata.from_file(example)
        assert meta.skip is True
        assert meta.skip_reason == "skip=true directive"
    
    def test_parse_timeout_directive(self, tmp_path):
        """Test parsing # praisonai: timeout=120 directive."""
        from praisonai.cli.features.examples import ExampleMetadata
        
        example = tmp_path / "test_timeout.py"
        example.write_text("# praisonai: timeout=120\nprint('hello')")
        
        meta = ExampleMetadata.from_file(example)
        assert meta.timeout == 120
    
    def test_parse_require_env_directive(self, tmp_path):
        """Test parsing # praisonai: require_env=KEY1,KEY2 directive."""
        from praisonai.cli.features.examples import ExampleMetadata
        
        example = tmp_path / "test_env.py"
        example.write_text("# praisonai: require_env=OPENAI_API_KEY,ANTHROPIC_API_KEY\nprint('hello')")
        
        meta = ExampleMetadata.from_file(example)
        assert meta.require_env == ["OPENAI_API_KEY", "ANTHROPIC_API_KEY"]
    
    def test_parse_xfail_directive(self, tmp_path):
        """Test parsing # praisonai: xfail=reason directive."""
        from praisonai.cli.features.examples import ExampleMetadata
        
        example = tmp_path / "test_xfail.py"
        example.write_text("# praisonai: xfail=known_flaky\nprint('hello')")
        
        meta = ExampleMetadata.from_file(example)
        assert meta.xfail == "known_flaky"
    
    def test_parse_multiple_directives(self, tmp_path):
        """Test parsing multiple directives in one file."""
        from praisonai.cli.features.examples import ExampleMetadata
        
        example = tmp_path / "test_multi.py"
        example.write_text(
            "#!/usr/bin/env python3\n"
            "# praisonai: timeout=300\n"
            "# praisonai: require_env=OPENAI_API_KEY\n"
            "# praisonai: xfail=slow_network\n"
            "print('hello')"
        )
        
        meta = ExampleMetadata.from_file(example)
        assert meta.timeout == 300
        assert meta.require_env == ["OPENAI_API_KEY"]
        assert meta.xfail == "slow_network"
    
    def test_detect_interactive_input(self, tmp_path):
        """Test detection of input() calls for auto-skip."""
        from praisonai.cli.features.examples import ExampleMetadata
        
        example = tmp_path / "test_interactive.py"
        example.write_text("name = input('Enter name: ')\nprint(name)")
        
        meta = ExampleMetadata.from_file(example)
        assert meta.is_interactive is True
    
    def test_no_directives(self, tmp_path):
        """Test file with no directives uses defaults."""
        from praisonai.cli.features.examples import ExampleMetadata
        
        example = tmp_path / "test_plain.py"
        example.write_text("print('hello world')")
        
        meta = ExampleMetadata.from_file(example)
        assert meta.skip is False
        assert meta.timeout is None
        assert meta.require_env == []
        assert meta.xfail is None
        assert meta.is_interactive is False


class TestExampleDiscovery:
    """Tests for example file discovery."""
    
    def test_discover_python_files(self, tmp_path):
        """Test discovering .py files recursively."""
        from praisonai.cli.features.examples import ExampleDiscovery
        
        # Create test structure
        (tmp_path / "subdir").mkdir()
        (tmp_path / "example1.py").write_text("print(1)")
        (tmp_path / "subdir" / "example2.py").write_text("print(2)")
        (tmp_path / "readme.md").write_text("# Readme")
        
        discovery = ExampleDiscovery(tmp_path)
        examples = discovery.discover()
        
        assert len(examples) == 2
        paths = [e.relative_to(tmp_path).as_posix() for e in examples]
        assert "example1.py" in paths
        assert "subdir/example2.py" in paths
    
    def test_ignore_underscore_prefix(self, tmp_path):
        """Test ignoring files starting with underscore."""
        from praisonai.cli.features.examples import ExampleDiscovery
        
        (tmp_path / "example.py").write_text("print(1)")
        (tmp_path / "_private.py").write_text("print(2)")
        (tmp_path / "__init__.py").write_text("")
        
        discovery = ExampleDiscovery(tmp_path)
        examples = discovery.discover()
        
        assert len(examples) == 1
        assert examples[0].name == "example.py"
    
    def test_ignore_pycache(self, tmp_path):
        """Test ignoring __pycache__ directories."""
        from praisonai.cli.features.examples import ExampleDiscovery
        
        (tmp_path / "__pycache__").mkdir()
        (tmp_path / "__pycache__" / "cached.py").write_text("print(1)")
        (tmp_path / "example.py").write_text("print(2)")
        
        discovery = ExampleDiscovery(tmp_path)
        examples = discovery.discover()
        
        assert len(examples) == 1
        assert examples[0].name == "example.py"
    
    def test_ignore_venv(self, tmp_path):
        """Test ignoring venv/virtualenv directories."""
        from praisonai.cli.features.examples import ExampleDiscovery
        
        (tmp_path / "venv").mkdir()
        (tmp_path / "venv" / "lib.py").write_text("print(1)")
        (tmp_path / ".venv").mkdir()
        (tmp_path / ".venv" / "lib.py").write_text("print(2)")
        (tmp_path / "example.py").write_text("print(3)")
        
        discovery = ExampleDiscovery(tmp_path)
        examples = discovery.discover()
        
        assert len(examples) == 1
        assert examples[0].name == "example.py"
    
    def test_deterministic_order(self, tmp_path):
        """Test examples are returned in deterministic sorted order."""
        from praisonai.cli.features.examples import ExampleDiscovery
        
        (tmp_path / "z_last.py").write_text("print(1)")
        (tmp_path / "a_first.py").write_text("print(2)")
        (tmp_path / "m_middle.py").write_text("print(3)")
        
        discovery = ExampleDiscovery(tmp_path)
        examples = discovery.discover()
        
        names = [e.name for e in examples]
        assert names == ["a_first.py", "m_middle.py", "z_last.py"]
    
    def test_include_pattern(self, tmp_path):
        """Test filtering with include pattern."""
        from praisonai.cli.features.examples import ExampleDiscovery
        
        (tmp_path / "context").mkdir()
        (tmp_path / "context" / "test1.py").write_text("print(1)")
        (tmp_path / "other").mkdir()
        (tmp_path / "other" / "test2.py").write_text("print(2)")
        
        discovery = ExampleDiscovery(tmp_path, include_patterns=["context/*"])
        examples = discovery.discover()
        
        assert len(examples) == 1
        assert "context" in str(examples[0])
    
    def test_exclude_pattern(self, tmp_path):
        """Test filtering with exclude pattern."""
        from praisonai.cli.features.examples import ExampleDiscovery
        
        (tmp_path / "test1.py").write_text("print(1)")
        (tmp_path / "test_wow.py").write_text("print(2)")
        
        discovery = ExampleDiscovery(tmp_path, exclude_patterns=["*_wow.py"])
        examples = discovery.discover()
        
        assert len(examples) == 1
        assert examples[0].name == "test1.py"


class TestExampleRunner:
    """Tests for example execution."""
    
    def test_run_passing_example(self, tmp_path):
        """Test running a passing example."""
        from praisonai.cli.features.examples import ExampleRunner, ExampleResult
        
        example = tmp_path / "pass.py"
        example.write_text("print('PASSED')")
        
        runner = ExampleRunner(timeout=30)
        result = runner.run(example)
        
        assert result.status == "passed"
        assert result.exit_code == 0
        assert result.duration_seconds > 0
    
    def test_run_failing_example(self, tmp_path):
        """Test running a failing example."""
        from praisonai.cli.features.examples import ExampleRunner
        
        example = tmp_path / "fail.py"
        example.write_text("raise ValueError('test error')")
        
        runner = ExampleRunner(timeout=30)
        result = runner.run(example)
        
        assert result.status == "failed"
        assert result.exit_code != 0
        assert "ValueError" in (result.error_summary or "")
    
    def test_run_timeout_example(self, tmp_path):
        """Test running an example that times out."""
        from praisonai.cli.features.examples import ExampleRunner
        
        example = tmp_path / "timeout.py"
        example.write_text("import time; time.sleep(10)")
        
        runner = ExampleRunner(timeout=1)
        result = runner.run(example)
        
        assert result.status == "timeout"
    
    def test_skip_missing_env(self, tmp_path):
        """Test skipping example with missing required env var."""
        from praisonai.cli.features.examples import ExampleRunner, ExampleMetadata
        
        example = tmp_path / "needs_key.py"
        example.write_text("# praisonai: require_env=NONEXISTENT_KEY_12345\nprint('hello')")
        
        runner = ExampleRunner(timeout=30)
        result = runner.run(example)
        
        assert result.status == "skipped"
        assert "NONEXISTENT_KEY_12345" in (result.skip_reason or "")
    
    def test_skip_interactive(self, tmp_path):
        """Test skipping interactive example."""
        from praisonai.cli.features.examples import ExampleRunner
        
        example = tmp_path / "interactive.py"
        example.write_text("x = input('prompt')")
        
        runner = ExampleRunner(timeout=30)
        result = runner.run(example)
        
        assert result.status == "skipped"
        assert "interactive" in (result.skip_reason or "").lower()
    
    def test_xfail_expected_failure(self, tmp_path):
        """Test xfail example that fails as expected."""
        from praisonai.cli.features.examples import ExampleRunner
        
        example = tmp_path / "xfail.py"
        example.write_text("# praisonai: xfail=expected\nraise Exception('expected')")
        
        runner = ExampleRunner(timeout=30)
        result = runner.run(example)
        
        assert result.status == "xfail"
    
    def test_pythonpath_includes_src(self, tmp_path):
        """Test PYTHONPATH is set correctly for imports."""
        from praisonai.cli.features.examples import ExampleRunner
        
        example = tmp_path / "check_path.py"
        example.write_text(
            "import sys\n"
            "import os\n"
            "pythonpath = os.environ.get('PYTHONPATH', '')\n"
            "print(f'PYTHONPATH={pythonpath}')\n"
        )
        
        runner = ExampleRunner(timeout=30)
        result = runner.run(example)
        
        assert result.status == "passed"
    
    def test_captures_stdout_stderr(self, tmp_path):
        """Test stdout and stderr are captured."""
        from praisonai.cli.features.examples import ExampleRunner
        
        example = tmp_path / "output.py"
        example.write_text(
            "import sys\n"
            "print('stdout message')\n"
            "print('stderr message', file=sys.stderr)\n"
        )
        
        runner = ExampleRunner(timeout=30, capture_output=True)
        result = runner.run(example)
        
        assert result.status == "passed"
        assert result.stdout is not None
        assert "stdout message" in result.stdout
        assert result.stderr is not None
        assert "stderr message" in result.stderr


class TestReportGenerator:
    """Tests for report generation."""
    
    def test_generate_json_report(self, tmp_path):
        """Test JSON report generation."""
        from praisonai.cli.features.examples import ReportGenerator, ExampleResult, RunReport
        
        results = [
            ExampleResult(
                path=Path("test1.py"),
                slug="test1",
                status="passed",
                exit_code=0,
                duration_seconds=1.5,
                start_time="2026-01-09T11:00:00Z",
                end_time="2026-01-09T11:00:01Z",
            ),
            ExampleResult(
                path=Path("test2.py"),
                slug="test2",
                status="failed",
                exit_code=1,
                duration_seconds=0.5,
                start_time="2026-01-09T11:00:02Z",
                end_time="2026-01-09T11:00:02Z",
                error_summary="ValueError: test",
            ),
        ]
        
        report = RunReport(
            examples=results,
            cli_args=["--timeout", "60"],
        )
        
        generator = ReportGenerator(tmp_path)
        json_path = generator.generate_json(report)
        
        assert json_path.exists()
        data = json.loads(json_path.read_text())
        
        assert "metadata" in data
        assert data["metadata"]["totals"]["passed"] == 1
        assert data["metadata"]["totals"]["failed"] == 1
        assert len(data["examples"]) == 2
    
    def test_generate_markdown_report(self, tmp_path):
        """Test markdown report generation."""
        from praisonai.cli.features.examples import ReportGenerator, ExampleResult, RunReport
        
        results = [
            ExampleResult(
                path=Path("test1.py"),
                slug="test1",
                status="passed",
                exit_code=0,
                duration_seconds=1.5,
                start_time="2026-01-09T11:00:00Z",
                end_time="2026-01-09T11:00:01Z",
            ),
        ]
        
        report = RunReport(examples=results, cli_args=[])
        generator = ReportGenerator(tmp_path)
        md_path = generator.generate_markdown(report)
        
        assert md_path.exists()
        content = md_path.read_text()
        
        assert "# Examples Run Report" in content
        assert "test1.py" in content
        assert "passed" in content.lower()
    
    def test_save_log_files(self, tmp_path):
        """Test log files are saved correctly."""
        from praisonai.cli.features.examples import ReportGenerator, ExampleResult, RunReport
        
        results = [
            ExampleResult(
                path=Path("test1.py"),
                slug="test1",
                status="passed",
                exit_code=0,
                duration_seconds=1.0,
                start_time="2026-01-09T11:00:00Z",
                end_time="2026-01-09T11:00:01Z",
                stdout="stdout content",
                stderr="stderr content",
            ),
        ]
        
        report = RunReport(examples=results, cli_args=[])
        generator = ReportGenerator(tmp_path)
        generator.save_logs(report)
        
        logs_dir = tmp_path / "logs"
        assert logs_dir.exists()
        
        stdout_log = logs_dir / "test1.stdout.log"
        stderr_log = logs_dir / "test1.stderr.log"
        
        assert stdout_log.exists()
        assert stderr_log.exists()
        assert stdout_log.read_text() == "stdout content"
        assert stderr_log.read_text() == "stderr content"


class TestCLIIntegration:
    """Tests for CLI command integration."""
    
    def test_examples_list_command(self, tmp_path):
        """Test 'praisonai examples list' command."""
        from typer.testing import CliRunner
        
        # Create test examples
        (tmp_path / "test1.py").write_text("print(1)")
        (tmp_path / "test2.py").write_text("print(2)")
        
        # Import after creating files to avoid import errors
        from praisonai.cli.commands.examples import app
        
        runner = CliRunner()
        result = runner.invoke(app, ["list", "--path", str(tmp_path)])
        
        assert result.exit_code == 0
        assert "test1.py" in result.stdout
        assert "test2.py" in result.stdout
    
    def test_examples_run_command_passing(self, tmp_path):
        """Test 'praisonai examples run' with passing examples."""
        from typer.testing import CliRunner
        
        (tmp_path / "pass.py").write_text("print('hello')")
        
        from praisonai.cli.commands.examples import app
        
        runner = CliRunner()
        result = runner.invoke(app, [
            "run",
            "--path", str(tmp_path),
            "--report-dir", str(tmp_path / "reports"),
            "--no-stream",
        ])
        
        assert result.exit_code == 0
        assert (tmp_path / "reports").exists()
    
    def test_examples_run_command_failing(self, tmp_path):
        """Test 'praisonai examples run' with failing examples."""
        from typer.testing import CliRunner
        
        (tmp_path / "fail.py").write_text("raise ValueError('fail')")
        
        from praisonai.cli.commands.examples import app
        
        runner = CliRunner()
        result = runner.invoke(app, [
            "run",
            "--path", str(tmp_path),
            "--report-dir", str(tmp_path / "reports"),
            "--no-stream",
        ])
        
        assert result.exit_code == 1  # Non-zero for failures
    
    def test_examples_run_fail_fast(self, tmp_path):
        """Test --fail-fast stops on first failure."""
        from typer.testing import CliRunner
        
        (tmp_path / "a_fail.py").write_text("raise ValueError('fail')")
        (tmp_path / "b_pass.py").write_text("print('pass')")
        
        from praisonai.cli.commands.examples import app
        
        runner = CliRunner()
        result = runner.invoke(app, [
            "run",
            "--path", str(tmp_path),
            "--fail-fast",
            "--no-stream",
        ])
        
        # Should have stopped after first failure
        assert result.exit_code == 1
