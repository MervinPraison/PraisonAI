"""CLI integration tests for praisonai docs commands."""


class TestCLIIntegration:
    """Tests for CLI command integration."""

    def test_docs_list_command(self, tmp_path):
        """Test 'praisonai docs list' command."""
        from typer.testing import CliRunner

        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()
        (docs_dir / "test.mdx").write_text("# Test\n```python\nprint(1)\n```")

        from praisonai.cli.commands.docs import app

        runner = CliRunner()
        result = runner.invoke(app, ["list", "--docs-path", str(docs_dir)])

        assert result.exit_code == 0
        assert "test.mdx" in result.stdout

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
        result = runner.invoke(
            app,
            [
                "run",
                "--docs-path",
                str(docs_dir),
                "--dry-run",
                "--report-dir",
                str(tmp_path / "reports"),
            ],
        )
        assert result.exit_code == 0

        report_path = tmp_path / "reports" / "report.json"
        assert report_path.exists()
        import json

        report = json.loads(report_path.read_text())
        dry_run_results = [
            r for r in report["results"] if r.get("skip_reason") == "Dry run"
        ]
        assert dry_run_results
        assert all(r["status"] == "not_run" for r in dry_run_results)
