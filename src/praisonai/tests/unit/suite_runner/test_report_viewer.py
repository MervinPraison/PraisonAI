"""
Unit tests for report_viewer module.

Tests cover:
- Latest report directory detection
- JSON parsing and loading
- Error signature normalization
- Error grouping
- Table rendering
- CLI integration smoke test
"""

import json
import pytest

from praisonai.suite_runner.report_viewer import (
    normalize_error_signature,
    find_latest_report_dir,
    find_report_files,
    load_report,
    group_errors,
    render_overview,
    render_failures_table,
    render_error_groups,
    view_report,
    _truncate,
    _render_table,
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def sample_report_json():
    """Sample report JSON structure."""
    return {
        "metadata": {
            "suite": "examples",
            "source_path": "/path/to/examples",
            "timestamp": "2026-01-09T14:26:07.808316+00:00",
            "platform": "Darwin-25.3.0-arm64",
            "python_version": "3.12.11",
            "python_executable": "/usr/bin/python",
            "praisonai_version": "3.5.8",
            "git_commit": "abc1234",
            "cli_args": [],
            "groups_run": ["acp", "tools"],
            "totals": {
                "passed": 5,
                "failed": 2,
                "skipped": 1,
                "timeout": 1,
                "not_run": 0,
                "xfail": 0,
                "total": 9,
            },
        },
        "results": [
            {
                "item_id": "acp__test1",
                "suite": "examples",
                "group": "acp",
                "source_path": "/path/to/examples/acp/test1.py",
                "block_index": 0,
                "language": "python",
                "status": "passed",
                "duration_seconds": 1.5,
                "exit_code": 0,
            },
            {
                "item_id": "acp__test2",
                "suite": "examples",
                "group": "acp",
                "source_path": "/path/to/examples/acp/test2.py",
                "block_index": 0,
                "language": "python",
                "status": "failed",
                "duration_seconds": 2.0,
                "exit_code": 1,
                "error_type": "ImportError",
                "error_message": "No module named 'missing_module'",
            },
            {
                "item_id": "tools__test3",
                "suite": "examples",
                "group": "tools",
                "source_path": "/path/to/examples/tools/test3.py",
                "block_index": 0,
                "language": "python",
                "status": "failed",
                "duration_seconds": 0.5,
                "exit_code": 1,
                "error_type": "ImportError",
                "error_message": "No module named 'missing_module'",
            },
            {
                "item_id": "tools__test4",
                "suite": "examples",
                "group": "tools",
                "source_path": "/path/to/examples/tools/test4.py",
                "block_index": 0,
                "language": "python",
                "status": "timeout",
                "duration_seconds": 60.0,
                "exit_code": -1,
                "error_type": "TimeoutError",
                "error_message": "Execution timed out after 60 seconds",
            },
        ],
    }


@pytest.fixture
def report_dir(tmp_path, sample_report_json):
    """Create a temporary report directory with sample data."""
    report_path = tmp_path / "report.json"
    report_path.write_text(json.dumps(sample_report_json), encoding='utf-8')
    return tmp_path


@pytest.fixture
def multi_group_report_dir(tmp_path, sample_report_json):
    """Create a report directory with multiple group subdirs."""
    # Create group subdirectories
    acp_dir = tmp_path / "acp"
    acp_dir.mkdir()
    tools_dir = tmp_path / "tools"
    tools_dir.mkdir()
    
    # Write separate reports for each group
    acp_report = {
        "metadata": sample_report_json["metadata"].copy(),
        "results": [r for r in sample_report_json["results"] if r["group"] == "acp"],
    }
    acp_report["metadata"]["groups_run"] = ["acp"]
    (acp_dir / "report.json").write_text(json.dumps(acp_report), encoding='utf-8')
    
    tools_report = {
        "metadata": sample_report_json["metadata"].copy(),
        "results": [r for r in sample_report_json["results"] if r["group"] == "tools"],
    }
    tools_report["metadata"]["groups_run"] = ["tools"]
    (tools_dir / "report.json").write_text(json.dumps(tools_report), encoding='utf-8')
    
    return tmp_path


# =============================================================================
# Error Signature Normalization Tests
# =============================================================================

class TestNormalizeErrorSignature:
    """Tests for error signature normalization."""
    
    def test_basic_error(self):
        """Test basic error type and message."""
        sig = normalize_error_signature("ImportError", "No module named 'foo'")
        assert "ImportError" in sig
        assert "No module named" in sig
    
    def test_strips_file_paths(self):
        """Test that file paths are normalized."""
        msg = 'File "/Users/praison/project/test.py", line 42, in foo'
        sig = normalize_error_signature("SyntaxError", msg)
        assert "/Users/praison" not in sig
        assert "...py" in sig or "line N" in sig
    
    def test_strips_line_numbers(self):
        """Test that line numbers are normalized."""
        msg = "Error at line 123 in function"
        sig = normalize_error_signature("Error", msg)
        assert "123" not in sig
        assert "line N" in sig
    
    def test_strips_memory_addresses(self):
        """Test that memory addresses are normalized."""
        msg = "Object at 0x7f8b1c2d3e4f crashed"
        sig = normalize_error_signature("RuntimeError", msg)
        assert "0x7f8b1c2d3e4f" not in sig
        assert "0x..." in sig
    
    def test_strips_uuids(self):
        """Test that UUIDs are normalized."""
        msg = "Request 550e8400-e29b-41d4-a716-446655440000 failed"
        sig = normalize_error_signature("Error", msg)
        assert "550e8400" not in sig
        assert "UUID" in sig
    
    def test_strips_timestamps(self):
        """Test that timestamps are normalized."""
        msg = "Error at 2026-01-09T14:30:00Z"
        sig = normalize_error_signature("Error", msg)
        assert "2026-01-09" not in sig
        assert "TIMESTAMP" in sig
    
    def test_empty_message(self):
        """Test with empty message."""
        sig = normalize_error_signature("Error", "")
        assert sig == "Error"
    
    def test_none_values(self):
        """Test with None values."""
        sig = normalize_error_signature(None, None)
        assert sig == "unknown_error"
    
    def test_truncates_long_messages(self):
        """Test that long messages are truncated."""
        long_msg = "x" * 200
        sig = normalize_error_signature("Error", long_msg)
        assert len(sig) <= 110  # Error: + 100 chars


# =============================================================================
# Report Discovery Tests
# =============================================================================

class TestFindLatestReportDir:
    """Tests for latest report directory detection."""
    
    def test_finds_direct_report(self, report_dir):
        """Test finding report.json directly in directory."""
        result = find_latest_report_dir("examples", report_dir)
        assert result == report_dir
    
    def test_finds_latest_by_mtime(self, tmp_path):
        """Test finding latest directory by modification time."""
        # Create older directory
        old_dir = tmp_path / "20260101_120000"
        old_dir.mkdir()
        (old_dir / "report.json").write_text('{"metadata": {}, "results": []}')
        
        # Create newer directory
        new_dir = tmp_path / "20260109_140000"
        new_dir.mkdir()
        (new_dir / "report.json").write_text('{"metadata": {}, "results": []}')
        
        result = find_latest_report_dir("examples", tmp_path)
        assert result == new_dir
    
    def test_returns_none_for_empty_dir(self, tmp_path):
        """Test returns None when no reports found."""
        result = find_latest_report_dir("examples", tmp_path)
        assert result is None
    
    def test_returns_none_for_nonexistent_dir(self, tmp_path):
        """Test returns None for nonexistent directory."""
        result = find_latest_report_dir("examples", tmp_path / "nonexistent")
        assert result is None


class TestFindReportFiles:
    """Tests for finding report files in a directory."""
    
    def test_finds_direct_report(self, report_dir):
        """Test finding report.json directly."""
        files = find_report_files(report_dir)
        assert len(files) == 1
        assert files[0].name == "report.json"
    
    def test_finds_group_reports(self, multi_group_report_dir):
        """Test finding reports in group subdirectories."""
        files = find_report_files(multi_group_report_dir)
        assert len(files) == 2
        names = {f.parent.name for f in files}
        assert names == {"acp", "tools"}


# =============================================================================
# Report Loading Tests
# =============================================================================

class TestLoadReport:
    """Tests for loading and parsing reports."""
    
    def test_loads_single_report(self, report_dir):
        """Test loading a single report.json."""
        report = load_report(report_dir)
        assert report.metadata.suite == "examples"
        assert len(report.items) == 4
    
    def test_loads_multi_group_report(self, multi_group_report_dir):
        """Test loading and aggregating multiple group reports."""
        report = load_report(multi_group_report_dir)
        assert len(report.items) == 4
        assert set(report.metadata.groups_run) == {"acp", "tools"}
    
    def test_calculates_totals(self, report_dir):
        """Test that totals are calculated correctly."""
        report = load_report(report_dir)
        totals = report.metadata.totals
        assert totals["passed"] == 1
        assert totals["failed"] == 2
        assert totals["timeout"] == 1
        assert totals["total"] == 4
    
    def test_raises_for_missing_report(self, tmp_path):
        """Test raises FileNotFoundError for missing report."""
        with pytest.raises(FileNotFoundError):
            load_report(tmp_path)
    
    def test_raises_for_invalid_json(self, tmp_path):
        """Test raises ValueError for invalid JSON."""
        (tmp_path / "report.json").write_text("not valid json")
        with pytest.raises(ValueError):
            load_report(tmp_path)
    
    def test_normalizes_error_signatures(self, report_dir):
        """Test that error signatures are normalized during load."""
        report = load_report(report_dir)
        failed_items = [i for i in report.items if i.status == "failed"]
        assert all(i.error_signature for i in failed_items)


# =============================================================================
# Error Grouping Tests
# =============================================================================

class TestGroupErrors:
    """Tests for error grouping functionality."""
    
    def test_groups_similar_errors(self, report_dir):
        """Test that similar errors are grouped together."""
        report = load_report(report_dir)
        groups = group_errors(report.items)
        
        # Should have 2 groups: ImportError and TimeoutError
        assert len(groups) == 2
    
    def test_counts_occurrences(self, report_dir):
        """Test that occurrence counts are correct."""
        report = load_report(report_dir)
        groups = group_errors(report.items)
        
        # Find ImportError group (should have 2 occurrences)
        import_group = next((g for g in groups if "ImportError" in g.error_type), None)
        assert import_group is not None
        assert import_group.count == 2
    
    def test_sorts_by_count_desc(self, report_dir):
        """Test that groups are sorted by count descending."""
        report = load_report(report_dir)
        groups = group_errors(report.items)
        
        counts = [g.count for g in groups]
        assert counts == sorted(counts, reverse=True)
    
    def test_ignores_passed_items(self, report_dir):
        """Test that passed items are not grouped."""
        report = load_report(report_dir)
        groups = group_errors(report.items)
        
        all_items = [i for g in groups for i in g.items]
        assert all(i.status in ("failed", "timeout", "error") for i in all_items)


# =============================================================================
# Rendering Tests
# =============================================================================

class TestTruncate:
    """Tests for text truncation."""
    
    def test_short_text_unchanged(self):
        """Test that short text is not truncated."""
        assert _truncate("hello", 10) == "hello"
    
    def test_long_text_truncated(self):
        """Test that long text is truncated with ellipsis."""
        result = _truncate("hello world", 8)
        assert len(result) == 8
        assert result.endswith("...")
    
    def test_empty_text(self):
        """Test empty text handling."""
        assert _truncate("", 10) == ""
        assert _truncate(None, 10) == ""
    
    def test_newlines_removed(self):
        """Test that newlines are removed."""
        assert "\n" not in _truncate("hello\nworld", 20)


class TestRenderTable:
    """Tests for ASCII table rendering."""
    
    def test_renders_headers(self):
        """Test that headers are rendered."""
        table = _render_table(["A", "B"], [["1", "2"]])
        assert "A" in table
        assert "B" in table
    
    def test_renders_data(self):
        """Test that data rows are rendered."""
        table = _render_table(["Col"], [["value1"], ["value2"]])
        assert "value1" in table
        assert "value2" in table
    
    def test_empty_table(self):
        """Test empty table handling."""
        table = _render_table([], [])
        assert table == ""


class TestRenderOverview:
    """Tests for overview rendering."""
    
    def test_includes_metadata(self, report_dir):
        """Test that overview includes metadata."""
        report = load_report(report_dir)
        output = render_overview(report)
        
        assert "EXAMPLES" in output.upper()
        assert "Python" in output or "python" in output
    
    def test_includes_totals(self, report_dir):
        """Test that overview includes totals."""
        report = load_report(report_dir)
        output = render_overview(report)
        
        assert "Passed" in output or "passed" in output
        assert "Failed" in output or "failed" in output


class TestRenderFailuresTable:
    """Tests for failures table rendering."""
    
    def test_shows_failures(self, report_dir):
        """Test that failures are shown."""
        report = load_report(report_dir)
        output = render_failures_table(report)
        
        assert "test2.py" in output or "test3.py" in output
    
    def test_respects_limit(self, report_dir):
        """Test that limit is respected."""
        report = load_report(report_dir)
        output = render_failures_table(report, limit=1)
        
        # Should mention there are more
        assert "more" in output.lower() or "1" in output
    
    def test_filters_by_status(self, report_dir):
        """Test filtering by status."""
        report = load_report(report_dir)
        output = render_failures_table(report, match_statuses=["timeout"])
        
        assert "timeout" in output.lower()


class TestRenderErrorGroups:
    """Tests for error groups rendering."""
    
    def test_shows_groups(self, report_dir):
        """Test that error groups are shown."""
        report = load_report(report_dir)
        output = render_error_groups(report)
        
        assert "ERROR GROUPS" in output
        assert "ImportError" in output or "TimeoutError" in output
    
    def test_shows_counts(self, report_dir):
        """Test that occurrence counts are shown."""
        report = load_report(report_dir)
        output = render_error_groups(report)
        
        assert "occurrence" in output.lower()


# =============================================================================
# Integration Tests
# =============================================================================

class TestViewReport:
    """Integration tests for view_report function."""
    
    def test_table_output(self, report_dir):
        """Test table output format."""
        output, exit_code = view_report(
            report_dir=report_dir,
            suite="examples",
            output_format="table",
        )
        
        assert "EXAMPLES" in output.upper()
        assert exit_code == 1  # Has failures
    
    def test_json_output(self, report_dir):
        """Test JSON output format."""
        output, exit_code = view_report(
            report_dir=report_dir,
            suite="examples",
            output_format="json",
        )
        
        data = json.loads(output)
        assert "metadata" in data
        assert "failures" in data
        assert "error_groups" in data
    
    def test_exit_code_zero_for_no_failures(self, tmp_path):
        """Test exit code is 0 when no failures."""
        report = {
            "metadata": {"suite": "examples", "totals": {"passed": 1, "total": 1}},
            "results": [
                {
                    "item_id": "test1",
                    "suite": "examples",
                    "group": "test",
                    "source_path": "/test.py",
                    "status": "passed",
                }
            ],
        }
        (tmp_path / "report.json").write_text(json.dumps(report))
        
        output, exit_code = view_report(report_dir=tmp_path, suite="examples")
        assert exit_code == 0
    
    def test_error_for_missing_report(self, tmp_path):
        """Test error message for missing report."""
        output, exit_code = view_report(
            report_dir=tmp_path / "nonexistent",
            suite="examples",
        )
        
        assert "Error" in output
        assert exit_code == 1
    
    def test_auto_detect_latest(self, tmp_path):
        """Test auto-detection of latest report."""
        # Create a report directory
        run_dir = tmp_path / "20260109_140000"
        run_dir.mkdir()
        report = {
            "metadata": {"suite": "examples", "totals": {"passed": 1, "total": 1}},
            "results": [
                {
                    "item_id": "test1",
                    "suite": "examples",
                    "group": "test",
                    "source_path": "/test.py",
                    "status": "passed",
                }
            ],
        }
        (run_dir / "report.json").write_text(json.dumps(report))
        
        output, exit_code = view_report(
            report_dir=None,
            suite="examples",
            base_dir=tmp_path,
        )
        
        assert "EXAMPLES" in output.upper()
        assert exit_code == 0
