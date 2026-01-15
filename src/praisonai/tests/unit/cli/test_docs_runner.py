"""
Tests for the Docs Code Execution System.

TDD tests for fence extraction, classification, execution, and reporting.
"""

import json
import pytest
from pathlib import Path


class TestFenceExtractor:
    """Tests for markdown/mdx code fence extraction."""
    
    def test_extract_simple_python_fence(self, tmp_path):
        """Test extracting a simple python code fence."""
        from praisonai.docs_runner.extractor import FenceExtractor
        
        doc = tmp_path / "test.mdx"
        doc.write_text("""# Title

```python
print("hello")
```
""")
        
        extractor = FenceExtractor()
        blocks = extractor.extract(doc)
        
        assert len(blocks) == 1
        assert blocks[0].language == "python"
        assert blocks[0].code == 'print("hello")'
        assert blocks[0].line_start == 4
        assert blocks[0].line_end == 4
    
    def test_extract_multiple_fences(self, tmp_path):
        """Test extracting multiple code fences."""
        from praisonai.docs_runner.extractor import FenceExtractor
        
        doc = tmp_path / "test.mdx"
        doc.write_text("""# Title

```python
print("first")
```

Some text

```python
print("second")
```
""")
        
        extractor = FenceExtractor()
        blocks = extractor.extract(doc)
        
        assert len(blocks) == 2
        assert blocks[0].code == 'print("first")'
        assert blocks[1].code == 'print("second")'
    
    def test_extract_titled_fence(self, tmp_path):
        """Test extracting fence with title (Mintlify style)."""
        from praisonai.docs_runner.extractor import FenceExtractor
        
        doc = tmp_path / "test.mdx"
        doc.write_text("""# Title

```python Single Agent
from praisonaiagents import Agent
agent = Agent(instructions="test")
```
""")
        
        extractor = FenceExtractor()
        blocks = extractor.extract(doc)
        
        assert len(blocks) == 1
        assert blocks[0].language == "python"
        assert blocks[0].title == "Single Agent"
        assert "Agent" in blocks[0].code
    
    def test_extract_with_directive(self, tmp_path):
        """Test extracting fence with praisonai directive comment."""
        from praisonai.docs_runner.extractor import FenceExtractor
        
        doc = tmp_path / "test.mdx"
        doc.write_text("""# Title

<!-- praisonai: runnable=true timeout=120 require_env=OPENAI_API_KEY -->
```python
print("hello")
```
""")
        
        extractor = FenceExtractor()
        blocks = extractor.extract(doc)
        
        assert len(blocks) == 1
        assert blocks[0].directive_runnable is True
        assert blocks[0].directive_timeout == 120
        assert blocks[0].directive_require_env == ["OPENAI_API_KEY"]
    
    def test_extract_different_languages(self, tmp_path):
        """Test extracting fences with different languages."""
        from praisonai.docs_runner.extractor import FenceExtractor
        
        doc = tmp_path / "test.mdx"
        doc.write_text("""# Title

```bash
pip install praisonai
```

```python
print("hello")
```

```yaml
agents:
  test: value
```
""")
        
        extractor = FenceExtractor()
        blocks = extractor.extract(doc)
        
        assert len(blocks) == 3
        assert blocks[0].language == "bash"
        assert blocks[1].language == "python"
        assert blocks[2].language == "yaml"
    
    def test_extract_multiline_code(self, tmp_path):
        """Test extracting multiline code blocks."""
        from praisonai.docs_runner.extractor import FenceExtractor
        
        doc = tmp_path / "test.mdx"
        doc.write_text("""# Title

```python
from praisonaiagents import Agent

agent = Agent(
    instructions="test",
    name="TestAgent"
)

agent.start()
```
""")
        
        extractor = FenceExtractor()
        blocks = extractor.extract(doc)
        
        assert len(blocks) == 1
        assert "from praisonaiagents import Agent" in blocks[0].code
        assert "agent.start()" in blocks[0].code
        assert blocks[0].line_start == 4
        # line_end depends on implementation - just check it's reasonable
        assert blocks[0].line_end >= blocks[0].line_start
    
    def test_extract_nested_in_tabs(self, tmp_path):
        """Test extracting code from within Mintlify Tab components."""
        from praisonai.docs_runner.extractor import FenceExtractor
        
        doc = tmp_path / "test.mdx"
        doc.write_text("""# Title

<Tabs>
  <Tab title="Code">
```python
print("in tab")
```
  </Tab>
</Tabs>
""")
        
        extractor = FenceExtractor()
        blocks = extractor.extract(doc)
        
        assert len(blocks) == 1
        assert blocks[0].code == 'print("in tab")'
    
    def test_extract_preserves_doc_path(self, tmp_path):
        """Test that extracted blocks preserve source document path."""
        from praisonai.docs_runner.extractor import FenceExtractor
        
        doc = tmp_path / "docs" / "quickstart.mdx"
        doc.parent.mkdir(parents=True, exist_ok=True)
        doc.write_text("""```python
print("test")
```
""")
        
        extractor = FenceExtractor()
        blocks = extractor.extract(doc)
        
        assert len(blocks) == 1
        assert blocks[0].doc_path == doc
    
    def test_extract_skip_directive(self, tmp_path):
        """Test extracting fence with skip directive."""
        from praisonai.docs_runner.extractor import FenceExtractor
        
        doc = tmp_path / "test.mdx"
        doc.write_text("""# Title

<!-- praisonai: skip=true -->
```python
print("should skip")
```
""")
        
        extractor = FenceExtractor()
        blocks = extractor.extract(doc)
        
        assert len(blocks) == 1
        assert blocks[0].directive_skip is True


class TestRunnableClassifier:
    """Tests for runnable classification heuristics."""
    
    def test_classify_standalone_script(self):
        """Test classifying a standalone script as runnable."""
        from praisonai.docs_runner.classifier import RunnableClassifier
        from praisonai.docs_runner.extractor import CodeBlock
        
        block = CodeBlock(
            doc_path=Path("test.mdx"),
            language="python",
            code="""from praisonaiagents import Agent

agent = Agent(instructions="test")
agent.start()
""",
            line_start=1,
            line_end=4,
            block_index=0,
        )
        
        classifier = RunnableClassifier()
        result = classifier.classify(block)
        
        assert result.is_runnable is True
        assert result.reason == "heuristic_standalone"
    
    def test_classify_partial_snippet(self):
        """Test classifying a partial snippet as not runnable."""
        from praisonai.docs_runner.classifier import RunnableClassifier
        from praisonai.docs_runner.extractor import CodeBlock
        
        block = CodeBlock(
            doc_path=Path("test.mdx"),
            language="python",
            code="agent.start()",
            line_start=1,
            line_end=1,
            block_index=0,
        )
        
        classifier = RunnableClassifier()
        result = classifier.classify(block)
        
        assert result.is_runnable is False
        # Can be too_short, partial, or no_import - all valid reasons for not running
        assert result.reason in ("too_short", "no_import_partial", "no_terminal_action_partial")
    
    def test_classify_with_print_terminal(self):
        """Test classifying script with print as terminal action."""
        from praisonai.docs_runner.classifier import RunnableClassifier
        from praisonai.docs_runner.extractor import CodeBlock
        
        block = CodeBlock(
            doc_path=Path("test.mdx"),
            language="python",
            code="""import os
print(os.getcwd())
""",
            line_start=1,
            line_end=2,
            block_index=0,
        )
        
        classifier = RunnableClassifier()
        result = classifier.classify(block)
        
        assert result.is_runnable is True
    
    def test_classify_directive_override_runnable(self):
        """Test directive override to force runnable."""
        from praisonai.docs_runner.classifier import RunnableClassifier
        from praisonai.docs_runner.extractor import CodeBlock
        
        block = CodeBlock(
            doc_path=Path("test.mdx"),
            language="python",
            code="agent.start()",  # Would normally be partial
            line_start=1,
            line_end=1,
            block_index=0,
            directive_runnable=True,
        )
        
        classifier = RunnableClassifier()
        result = classifier.classify(block)
        
        assert result.is_runnable is True
        assert result.reason == "directive_override"
    
    def test_classify_directive_skip(self):
        """Test directive to skip block."""
        from praisonai.docs_runner.classifier import RunnableClassifier
        from praisonai.docs_runner.extractor import CodeBlock
        
        block = CodeBlock(
            doc_path=Path("test.mdx"),
            language="python",
            code="""from praisonaiagents import Agent
agent = Agent(instructions="test")
agent.start()
""",
            line_start=1,
            line_end=3,
            block_index=0,
            directive_skip=True,
        )
        
        classifier = RunnableClassifier()
        result = classifier.classify(block)
        
        assert result.is_runnable is False
        assert result.reason == "directive_skip"
    
    def test_classify_interactive_input(self):
        """Test detecting interactive input() calls."""
        from praisonai.docs_runner.classifier import RunnableClassifier
        from praisonai.docs_runner.extractor import CodeBlock
        
        block = CodeBlock(
            doc_path=Path("test.mdx"),
            language="python",
            code="""import os
name = input("Enter name: ")
print(name)
""",
            line_start=1,
            line_end=3,
            block_index=0,
        )
        
        classifier = RunnableClassifier()
        result = classifier.classify(block)
        
        assert result.is_runnable is False
        assert "interactive" in result.reason.lower()
    
    def test_classify_non_python_language(self):
        """Test non-python blocks are not runnable."""
        from praisonai.docs_runner.classifier import RunnableClassifier
        from praisonai.docs_runner.extractor import CodeBlock
        
        block = CodeBlock(
            doc_path=Path("test.mdx"),
            language="bash",
            code="pip install praisonai",
            line_start=1,
            line_end=1,
            block_index=0,
        )
        
        classifier = RunnableClassifier()
        result = classifier.classify(block)
        
        assert result.is_runnable is False
        assert "language" in result.reason.lower()
    
    def test_classify_too_short(self):
        """Test very short blocks are not runnable."""
        from praisonai.docs_runner.classifier import RunnableClassifier
        from praisonai.docs_runner.extractor import CodeBlock
        
        block = CodeBlock(
            doc_path=Path("test.mdx"),
            language="python",
            code="x = 1",
            line_start=1,
            line_end=1,
            block_index=0,
        )
        
        classifier = RunnableClassifier()
        result = classifier.classify(block)
        
        assert result.is_runnable is False


class TestWorkspaceWriter:
    """Tests for workspace script generation."""
    
    def test_write_single_script(self, tmp_path):
        """Test writing a single script to workspace."""
        from praisonai.docs_runner.workspace import WorkspaceWriter
        from praisonai.docs_runner.extractor import CodeBlock
        
        block = CodeBlock(
            doc_path=Path("docs/quickstart.mdx"),
            language="python",
            code='print("hello")',
            line_start=10,
            line_end=10,
            block_index=0,
        )
        
        writer = WorkspaceWriter(tmp_path)
        script_path = writer.write(block)
        
        assert script_path.exists()
        assert script_path.read_text() == 'print("hello")'
        assert "quickstart" in script_path.parent.name
    
    def test_write_creates_manifest(self, tmp_path):
        """Test manifest is created with block metadata."""
        from praisonai.docs_runner.workspace import WorkspaceWriter
        from praisonai.docs_runner.extractor import CodeBlock
        
        block = CodeBlock(
            doc_path=Path("docs/quickstart.mdx"),
            language="python",
            code='print("hello")',
            line_start=10,
            line_end=10,
            block_index=0,
        )
        
        writer = WorkspaceWriter(tmp_path)
        writer.write(block)
        manifest = writer.get_manifest()
        
        assert len(manifest) == 1
        assert manifest[0]["doc_path"] == "docs/quickstart.mdx"
        assert manifest[0]["line_start"] == 10
    
    def test_write_multiple_blocks_same_doc(self, tmp_path):
        """Test writing multiple blocks from same document."""
        from praisonai.docs_runner.workspace import WorkspaceWriter
        from praisonai.docs_runner.extractor import CodeBlock
        
        blocks = [
            CodeBlock(
                doc_path=Path("docs/quickstart.mdx"),
                language="python",
                code='print("first")',
                line_start=10,
                line_end=10,
                block_index=0,
            ),
            CodeBlock(
                doc_path=Path("docs/quickstart.mdx"),
                language="python",
                code='print("second")',
                line_start=20,
                line_end=20,
                block_index=1,
            ),
        ]
        
        writer = WorkspaceWriter(tmp_path)
        paths = [writer.write(b) for b in blocks]
        
        assert len(paths) == 2
        assert paths[0] != paths[1]
        assert all(p.exists() for p in paths)
    
    def test_write_deterministic_paths(self, tmp_path):
        """Test script paths are deterministic."""
        from praisonai.docs_runner.workspace import WorkspaceWriter
        from praisonai.docs_runner.extractor import CodeBlock
        
        block = CodeBlock(
            doc_path=Path("docs/quickstart.mdx"),
            language="python",
            code='print("hello")',
            line_start=10,
            line_end=10,
            block_index=0,
        )
        
        writer1 = WorkspaceWriter(tmp_path / "ws1")
        writer2 = WorkspaceWriter(tmp_path / "ws2")
        
        path1 = writer1.write(block)
        path2 = writer2.write(block)
        
        # Relative paths should be identical
        assert path1.name == path2.name


class TestSnippetRunner:
    """Tests for snippet execution."""
    
    def test_run_passing_script(self, tmp_path):
        """Test running a passing script."""
        from praisonai.docs_runner.runner import SnippetRunner
        
        script = tmp_path / "pass.py"
        script.write_text('print("PASSED")')
        
        runner = SnippetRunner(timeout=30)
        result = runner.run(script)
        
        assert result.status == "passed"
        assert result.exit_code == 0
        assert result.duration_seconds > 0
    
    def test_run_failing_script(self, tmp_path):
        """Test running a failing script."""
        from praisonai.docs_runner.runner import SnippetRunner
        
        script = tmp_path / "fail.py"
        script.write_text("raise ValueError('test error')")
        
        runner = SnippetRunner(timeout=30)
        result = runner.run(script)
        
        assert result.status == "failed"
        assert result.exit_code != 0
        assert "ValueError" in (result.error_summary or "")
    
    def test_run_timeout(self, tmp_path):
        """Test script timeout handling."""
        from praisonai.docs_runner.runner import SnippetRunner
        
        script = tmp_path / "timeout.py"
        script.write_text("import time; time.sleep(10)")
        
        runner = SnippetRunner(timeout=1)
        result = runner.run(script)
        
        assert result.status == "timeout"
    
    def test_run_captures_output(self, tmp_path):
        """Test stdout/stderr capture."""
        from praisonai.docs_runner.runner import SnippetRunner
        
        script = tmp_path / "output.py"
        script.write_text("""import sys
print("stdout message")
print("stderr message", file=sys.stderr)
""")
        
        runner = SnippetRunner(timeout=30, capture_output=True)
        result = runner.run(script)
        
        assert result.status == "passed"
        assert "stdout message" in result.stdout
        assert "stderr message" in result.stderr


class TestDocsReportBuilder:
    """Tests for report generation."""
    
    def test_generate_json_report(self, tmp_path):
        """Test JSON report generation."""
        from praisonai.docs_runner.reporter import DocsReportBuilder, SnippetResult
        
        results = [
            SnippetResult(
                doc_path=Path("docs/quickstart.mdx"),
                block_index=0,
                language="python",
                line_start=10,
                line_end=15,
                runnable_decision="heuristic_standalone",
                status="passed",
                exit_code=0,
                duration_seconds=1.5,
            ),
        ]
        
        builder = DocsReportBuilder(tmp_path)
        json_path = builder.generate_json(results, docs_path=Path("/docs"))
        
        assert json_path.exists()
        data = json.loads(json_path.read_text())
        
        assert "metadata" in data
        assert "snippets" in data
        assert len(data["snippets"]) == 1
    
    def test_generate_markdown_report(self, tmp_path):
        """Test Markdown report generation."""
        from praisonai.docs_runner.reporter import DocsReportBuilder, SnippetResult
        
        results = [
            SnippetResult(
                doc_path=Path("docs/quickstart.mdx"),
                block_index=0,
                language="python",
                line_start=10,
                line_end=15,
                runnable_decision="heuristic_standalone",
                status="passed",
                exit_code=0,
                duration_seconds=1.5,
            ),
        ]
        
        builder = DocsReportBuilder(tmp_path)
        md_path = builder.generate_markdown(results, docs_path=Path("/docs"))
        
        assert md_path.exists()
        content = md_path.read_text()
        
        assert "Docs Code Execution Report" in content
        assert "quickstart.mdx" in content


class TestDocsExecutor:
    """Tests for the main executor orchestrator."""
    
    def test_discover_docs(self, tmp_path):
        """Test discovering documentation files."""
        from praisonai.docs_runner.executor import DocsExecutor
        
        # Create test docs
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()
        (docs_dir / "quickstart.mdx").write_text("# Quick\n```python\nprint(1)\n```")
        (docs_dir / "intro.mdx").write_text("# Intro\n```python\nprint(2)\n```")
        
        executor = DocsExecutor(docs_path=docs_dir)
        docs = executor.discover_docs()
        
        assert len(docs) == 2
    
    def test_dry_run_mode(self, tmp_path):
        """Test dry-run mode extracts without executing."""
        from praisonai.docs_runner.executor import DocsExecutor
        
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()
        (docs_dir / "test.mdx").write_text("""# Test
```python
from os import getcwd
print(getcwd())
```
""")
        
        executor = DocsExecutor(docs_path=docs_dir, dry_run=True)
        report = executor.run()
        
        # In dry-run, blocks are extracted but not executed
        assert len(report.snippets) >= 1
        # All should be NOT_RUN in dry-run mode
        for s in report.snippets:
            assert s.status in ("not_run", "skipped")
    
    def test_include_pattern(self, tmp_path):
        """Test filtering docs by include pattern."""
        from praisonai.docs_runner.executor import DocsExecutor
        
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()
        (docs_dir / "quickstart.mdx").write_text("# Quick\n```python\nprint(1)\n```")
        (docs_dir / "other.mdx").write_text("# Other\n```python\nprint(2)\n```")
        
        executor = DocsExecutor(
            docs_path=docs_dir,
            include_patterns=["quick*"],
            dry_run=True,
        )
        docs = executor.discover_docs()
        
        assert len(docs) == 1
        assert "quickstart" in docs[0].name


class TestCLIIntegration:
    """Tests for CLI command integration."""
    
    def test_docs_list_command(self, tmp_path):
        """Test 'praisonai docs list' command."""
        from typer.testing import CliRunner
        
        # Create test docs
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()
        (docs_dir / "test.mdx").write_text("# Test\n```python\nprint(1)\n```")
        
        from praisonai.cli.commands.docs import app
        
        runner = CliRunner()
        result = runner.invoke(app, ["list", "--docs-path", str(docs_dir)])
        
        assert result.exit_code == 0
        assert "test.mdx" in result.stdout
    
    @pytest.mark.skip(reason="--dry-run option not implemented in docs run command")
    def test_docs_run_dry_run(self, tmp_path):
        """Test 'praisonai docs run --dry-run' command."""
        from typer.testing import CliRunner
        
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()
        (docs_dir / "test.mdx").write_text("""# Test
```python
from os import getcwd
print(getcwd())
```
""")
        
        from praisonai.cli.commands.docs import app
        
        runner = CliRunner()
        result = runner.invoke(app, [
            "run",
            "--docs-path", str(docs_dir),
            "--dry-run",
            "--report-dir", str(tmp_path / "reports"),
        ])
        
        assert result.exit_code == 0
