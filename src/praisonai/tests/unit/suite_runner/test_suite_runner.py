"""
Tests for the unified suite_runner engine.

Tests shared infrastructure used by both examples and docs runners.
"""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

class TestRunItem:
    """Tests for RunItem dataclass."""
    
    def test_create_run_item(self):
        """Test creating a RunItem."""
        from praisonai.suite_runner import RunItem
        
        item = RunItem(
            item_id="test_item",
            suite="examples",
            group="test_group",
            source_path=Path("/test/path.py"),
            code="print('hello')",
        )
        
        assert item.item_id == "test_item"
        assert item.suite == "examples"
        assert item.group == "test_group"
        assert item.runnable is True
        assert item.code_hash  # Should have a hash
    
    def test_display_name_examples(self):
        """Test display_name for examples."""
        from praisonai.suite_runner import RunItem
        
        item = RunItem(
            item_id="test",
            suite="examples",
            group="test",
            source_path=Path("/test/example.py"),
        )
        
        assert item.display_name == "example.py"
    
    def test_display_name_docs(self):
        """Test display_name for docs."""
        from praisonai.suite_runner import RunItem
        
        item = RunItem(
            item_id="test",
            suite="docs",
            group="test",
            source_path=Path("/test/doc.mdx"),
            block_index=2,
        )
        
        assert item.display_name == "doc.mdx:2"


class TestRunResult:
    """Tests for RunResult dataclass."""
    
    def test_create_run_result(self):
        """Test creating a RunResult."""
        from praisonai.suite_runner import RunResult
        
        result = RunResult(
            item_id="test",
            suite="examples",
            group="test",
            source_path=Path("/test/path.py"),
            status="passed",
            exit_code=0,
            duration_seconds=1.5,
        )
        
        assert result.status == "passed"
        assert result.exit_code == 0
        assert result.duration_seconds == 1.5


class TestRunReport:
    """Tests for RunReport dataclass."""
    
    def test_create_run_report(self):
        """Test creating a RunReport."""
        from praisonai.suite_runner import RunReport, RunResult
        
        results = [
            RunResult(item_id="1", suite="examples", group="a", source_path=Path("/a"), status="passed"),
            RunResult(item_id="2", suite="examples", group="a", source_path=Path("/b"), status="failed"),
            RunResult(item_id="3", suite="examples", group="b", source_path=Path("/c"), status="skipped"),
        ]
        
        report = RunReport(results=results, suite="examples", source_path=Path("/test"))
        
        totals = report.totals
        assert totals["passed"] == 1
        assert totals["failed"] == 1
        assert totals["skipped"] == 1
    
    def test_to_dict(self):
        """Test converting report to dict."""
        from praisonai.suite_runner import RunReport, RunResult
        
        results = [
            RunResult(item_id="1", suite="examples", group="a", source_path=Path("/a"), status="passed"),
        ]
        
        report = RunReport(results=results, suite="examples", source_path=Path("/test"))
        data = report.to_dict()
        
        assert "metadata" in data
        assert "results" in data
        assert data["metadata"]["suite"] == "examples"
        assert len(data["results"]) == 1


class TestFileDiscovery:
    """Tests for FileDiscovery."""
    
    def test_discover_python_files(self):
        """Test discovering Python files."""
        from praisonai.suite_runner import FileDiscovery
        
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create test files
            Path(tmpdir, "test1.py").write_text("# test")
            Path(tmpdir, "test2.py").write_text("# test")
            Path(tmpdir, "_private.py").write_text("# test")
            Path(tmpdir, "subdir").mkdir()
            Path(tmpdir, "subdir", "test3.py").write_text("# test")
            
            discovery = FileDiscovery(root=tmpdir, extensions=[".py"])
            files = discovery.discover()
            
            # Should find test1, test2, test3 but not _private
            assert len(files) == 3
            names = [f.name for f in files]
            assert "test1.py" in names
            assert "test2.py" in names
            assert "test3.py" in names
            assert "_private.py" not in names
    
    def test_discover_by_group(self):
        """Test discovering files by group."""
        from praisonai.suite_runner import FileDiscovery
        
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create test structure
            Path(tmpdir, "group_a").mkdir()
            Path(tmpdir, "group_b").mkdir()
            Path(tmpdir, "group_a", "test1.py").write_text("# test")
            Path(tmpdir, "group_b", "test2.py").write_text("# test")
            
            discovery = FileDiscovery(root=tmpdir, extensions=[".py"])
            grouped = discovery.discover_by_group(groups=["group_a"])
            
            assert "group_a" in grouped
            assert "group_b" not in grouped
            assert len(grouped["group_a"]) == 1
    
    def test_get_groups(self):
        """Test getting available groups."""
        from praisonai.suite_runner import FileDiscovery
        
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, "alpha").mkdir()
            Path(tmpdir, "beta").mkdir()
            Path(tmpdir, "alpha", "test.py").write_text("# test")
            Path(tmpdir, "beta", "test.py").write_text("# test")
            
            discovery = FileDiscovery(root=tmpdir, extensions=[".py"])
            groups = discovery.get_groups()
            
            assert "alpha" in groups
            assert "beta" in groups


class TestScriptRunner:
    """Tests for ScriptRunner."""
    
    def test_run_passing_script(self):
        """Test running a passing script."""
        from praisonai.suite_runner import ScriptRunner, RunItem
        
        with tempfile.TemporaryDirectory() as tmpdir:
            script = Path(tmpdir, "test.py")
            script.write_text("print('hello')")
            
            item = RunItem(
                item_id="test",
                suite="examples",
                group="test",
                source_path=script,
                script_path=script,
            )
            
            runner = ScriptRunner(timeout=10)
            result = runner.run(item)
            
            assert result.status == "passed"
            assert result.exit_code == 0
            assert "hello" in result.stdout
    
    def test_run_failing_script(self):
        """Test running a failing script."""
        from praisonai.suite_runner import ScriptRunner, RunItem
        
        with tempfile.TemporaryDirectory() as tmpdir:
            script = Path(tmpdir, "test.py")
            script.write_text("raise ValueError('test error')")
            
            item = RunItem(
                item_id="test",
                suite="examples",
                group="test",
                source_path=script,
                script_path=script,
            )
            
            runner = ScriptRunner(timeout=10)
            result = runner.run(item)
            
            assert result.status == "failed"
            assert result.exit_code != 0
            assert "ValueError" in (result.error_message or "")
    
    def test_run_timeout(self):
        """Test script timeout."""
        from praisonai.suite_runner import ScriptRunner, RunItem
        
        with tempfile.TemporaryDirectory() as tmpdir:
            script = Path(tmpdir, "test.py")
            script.write_text("import time; time.sleep(10)")
            
            item = RunItem(
                item_id="test",
                suite="examples",
                group="test",
                source_path=script,
                script_path=script,
            )
            
            runner = ScriptRunner(timeout=1)
            result = runner.run(item)
            
            assert result.status == "timeout"
    
    def test_check_required_env(self):
        """Test checking required environment variables."""
        from praisonai.suite_runner import ScriptRunner
        
        runner = ScriptRunner()
        
        # Should return None if env var exists
        with patch.dict(os.environ, {"TEST_VAR": "value"}):
            assert runner.check_required_env(["TEST_VAR"]) is None
        
        # Should return missing var name
        result = runner.check_required_env(["NONEXISTENT_VAR_12345"])
        assert result == "NONEXISTENT_VAR_12345"


class TestSuiteReporter:
    """Tests for SuiteReporter."""
    
    def test_generate_json(self):
        """Test generating JSON report."""
        from praisonai.suite_runner import SuiteReporter, RunReport, RunResult
        
        with tempfile.TemporaryDirectory() as tmpdir:
            results = [
                RunResult(item_id="1", suite="examples", group="a", source_path=Path("/a"), status="passed"),
            ]
            report = RunReport(results=results, suite="examples", source_path=Path("/test"))
            
            reporter = SuiteReporter(Path(tmpdir))
            json_path = reporter.generate_json(report)
            
            assert json_path.exists()
            assert json_path.name == "report.json"
    
    def test_generate_markdown(self):
        """Test generating Markdown report."""
        from praisonai.suite_runner import SuiteReporter, RunReport, RunResult
        
        with tempfile.TemporaryDirectory() as tmpdir:
            results = [
                RunResult(item_id="1", suite="examples", group="a", source_path=Path("/a"), status="passed"),
            ]
            report = RunReport(results=results, suite="examples", source_path=Path("/test"))
            
            reporter = SuiteReporter(Path(tmpdir))
            md_path = reporter.generate_markdown(report)
            
            assert md_path.exists()
            assert md_path.name == "report.md"
            content = md_path.read_text()
            assert "Examples Execution Report" in content
    
    def test_generate_csv(self):
        """Test generating CSV report."""
        from praisonai.suite_runner import SuiteReporter, RunReport, RunResult
        
        with tempfile.TemporaryDirectory() as tmpdir:
            results = [
                RunResult(item_id="1", suite="examples", group="a", source_path=Path("/a"), status="passed"),
                RunResult(item_id="2", suite="examples", group="b", source_path=Path("/b"), status="failed"),
            ]
            report = RunReport(results=results, suite="examples", source_path=Path("/test"))
            
            reporter = SuiteReporter(Path(tmpdir))
            csv_path = reporter.generate_csv(report)
            
            assert csv_path.exists()
            assert csv_path.name == "report.csv"
            content = csv_path.read_text()
            assert "suite,group,item_id" in content
            assert "passed" in content
            assert "failed" in content
    
    def test_save_logs(self):
        """Test saving logs."""
        from praisonai.suite_runner import SuiteReporter, RunResult
        
        with tempfile.TemporaryDirectory() as tmpdir:
            results = [
                RunResult(
                    item_id="1",
                    suite="examples",
                    group="a",
                    source_path=Path("/test.py"),
                    status="passed",
                    stdout="hello stdout",
                    stderr="hello stderr",
                ),
            ]
            
            reporter = SuiteReporter(Path(tmpdir))
            logs_dir = reporter.save_logs(results)
            
            assert logs_dir.exists()
            assert (logs_dir / "test.stdout.log").exists()
            assert (logs_dir / "test.stderr.log").exists()


class TestExamplesSource:
    """Tests for ExamplesSource."""
    
    def test_discover_examples(self):
        """Test discovering examples."""
        from praisonai.suite_runner import ExamplesSource
        
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create test examples
            Path(tmpdir, "group_a").mkdir()
            Path(tmpdir, "group_a", "example1.py").write_text("print('hello')")
            Path(tmpdir, "group_a", "example2.py").write_text("print('world')")
            
            source = ExamplesSource(root=tmpdir)
            items = source.discover()
            
            assert len(items) == 2
            assert all(item.suite == "examples" for item in items)
    
    def test_parse_directives(self):
        """Test parsing directives from examples."""
        from praisonai.suite_runner import ExamplesSource
        
        with tempfile.TemporaryDirectory() as tmpdir:
            example = Path(tmpdir, "test.py")
            example.write_text("""# praisonai: skip=true
# praisonai: timeout=120
print('hello')
""")
            
            source = ExamplesSource(root=tmpdir)
            items = source.discover()
            
            assert len(items) == 1
            item = items[0]
            assert item.skip is True
            assert item.timeout == 120
    
    def test_detect_interactive(self):
        """Test detecting interactive examples."""
        from praisonai.suite_runner import ExamplesSource
        
        with tempfile.TemporaryDirectory() as tmpdir:
            example = Path(tmpdir, "test.py")
            example.write_text("name = input('Enter name: ')")
            
            source = ExamplesSource(root=tmpdir)
            items = source.discover()
            
            assert len(items) == 1
            assert items[0].is_interactive is True
            assert items[0].runnable is False


class TestDocsSource:
    """Tests for DocsSource."""
    
    def test_extract_code_blocks(self):
        """Test extracting code blocks from docs."""
        from praisonai.suite_runner import DocsSource
        
        with tempfile.TemporaryDirectory() as tmpdir:
            doc = Path(tmpdir, "test.mdx")
            doc.write_text("""# Test Doc

```python
from praisonaiagents import Agent
agent = Agent()
agent.start("Hello")
```

Some text

```python
print("partial")
```
""")
            
            source = DocsSource(root=tmpdir)
            items = source.discover()
            
            assert len(items) == 2
            assert all(item.suite == "docs" for item in items)
            # First block should be runnable (has import + terminal action)
            assert items[0].runnable is True
            # Second block is partial (no import)
            assert items[1].runnable is False
    
    def test_parse_directive(self):
        """Test parsing directives from docs."""
        from praisonai.suite_runner import DocsSource
        
        with tempfile.TemporaryDirectory() as tmpdir:
            doc = Path(tmpdir, "test.mdx")
            doc.write_text("""# Test

<!-- praisonai: skip=true timeout=120 -->
```python
print("hello")
```
""")
            
            source = DocsSource(root=tmpdir)
            items = source.discover()
            
            assert len(items) == 1
            item = items[0]
            assert item.skip is True
            assert item.timeout == 120
    
    def test_dedent_indented_code(self):
        """Test that indented code blocks are dedented."""
        from praisonai.suite_runner import DocsSource
        
        with tempfile.TemporaryDirectory() as tmpdir:
            doc = Path(tmpdir, "test.mdx")
            doc.write_text("""# Test

<Tab>
    ```python
    from praisonaiagents import Agent
    agent = Agent()
    agent.start("test")
    ```
</Tab>
""")
            
            source = DocsSource(root=tmpdir)
            items = source.discover()
            
            assert len(items) == 1
            # Code should be dedented
            assert not items[0].code.startswith("    ")
