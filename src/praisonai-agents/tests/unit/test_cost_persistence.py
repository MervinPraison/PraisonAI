"""Tests for Cost Dashboard persistence (F4).

Tests save/load/list/format for cost reports in ~/.praisonai/costs/.
"""

import json
import os
import tempfile
import time
import pytest
from unittest.mock import MagicMock, patch
from pathlib import Path


class TestSaveCostReport:
    """Test saving cost reports to disk."""

    def test_save_creates_file(self, tmp_path):
        from praisonaiagents.agent.cost_persistence import save_cost_report
        agent = MagicMock()
        agent.name = "test_agent"
        agent.cost_summary = {"tokens_in": 100, "tokens_out": 50, "cost": 0.001, "llm_calls": 1}
        with patch("praisonaiagents.agent.cost_persistence.COST_DIR", tmp_path):
            filepath = save_cost_report(agent, session_name="test_session")
            assert os.path.exists(filepath)

    def test_save_content(self, tmp_path):
        from praisonaiagents.agent.cost_persistence import save_cost_report
        agent = MagicMock()
        agent.name = "my_agent"
        agent.cost_summary = {"tokens_in": 500, "tokens_out": 200, "cost": 0.05, "llm_calls": 3}
        with patch("praisonaiagents.agent.cost_persistence.COST_DIR", tmp_path):
            filepath = save_cost_report(agent, session_name="s1")
            with open(filepath) as f:
                data = json.load(f)
            assert data["agent_name"] == "my_agent"
            assert data["cost"] == 0.05
            assert data["tokens_in"] == 500
            assert data["llm_calls"] == 3

    def test_save_auto_session_name(self, tmp_path):
        from praisonaiagents.agent.cost_persistence import save_cost_report
        agent = MagicMock()
        agent.name = "bot"
        agent.cost_summary = {"tokens_in": 0, "tokens_out": 0, "cost": 0.0, "llm_calls": 0}
        with patch("praisonaiagents.agent.cost_persistence.COST_DIR", tmp_path):
            filepath = save_cost_report(agent)
            assert "bot_" in filepath


class TestLoadCostReport:
    """Test loading cost reports from disk."""

    def test_load_existing(self, tmp_path):
        from praisonaiagents.agent.cost_persistence import load_cost_report
        data = {"session": "test", "cost": 0.01}
        (tmp_path / "test.json").write_text(json.dumps(data))
        with patch("praisonaiagents.agent.cost_persistence.COST_DIR", tmp_path):
            result = load_cost_report("test")
            assert result["cost"] == 0.01

    def test_load_missing(self, tmp_path):
        from praisonaiagents.agent.cost_persistence import load_cost_report
        with patch("praisonaiagents.agent.cost_persistence.COST_DIR", tmp_path):
            result = load_cost_report("nonexistent")
            assert result is None


class TestListCostReports:
    """Test listing cost reports."""

    def test_list_empty(self, tmp_path):
        from praisonaiagents.agent.cost_persistence import list_cost_reports
        with patch("praisonaiagents.agent.cost_persistence.COST_DIR", tmp_path):
            results = list_cost_reports()
            assert results == []

    def test_list_multiple(self, tmp_path):
        from praisonaiagents.agent.cost_persistence import list_cost_reports
        for i in range(3):
            data = {"session": f"s{i}", "cost": i * 0.01}
            (tmp_path / f"s{i}.json").write_text(json.dumps(data))
        with patch("praisonaiagents.agent.cost_persistence.COST_DIR", tmp_path):
            results = list_cost_reports()
            assert len(results) == 3

    def test_list_limit(self, tmp_path):
        from praisonaiagents.agent.cost_persistence import list_cost_reports
        for i in range(10):
            data = {"session": f"s{i}", "cost": i * 0.01}
            (tmp_path / f"s{i}.json").write_text(json.dumps(data))
        with patch("praisonaiagents.agent.cost_persistence.COST_DIR", tmp_path):
            results = list_cost_reports(limit=5)
            assert len(results) == 5


class TestFormatCostTable:
    """Test terminal formatting."""

    def test_format_empty(self):
        from praisonaiagents.agent.cost_persistence import format_cost_table
        assert format_cost_table([]) == "No cost reports found."

    def test_format_as_json(self):
        from praisonaiagents.agent.cost_persistence import format_cost_table
        reports = [{"session": "s1", "cost": 0.01}]
        result = format_cost_table(reports, as_json=True)
        parsed = json.loads(result)
        assert parsed[0]["cost"] == 0.01

    def test_format_table(self):
        from praisonaiagents.agent.cost_persistence import format_cost_table
        reports = [{"session": "s1", "agent_name": "bot", "cost": 0.05, "tokens_in": 100, "tokens_out": 50, "llm_calls": 2}]
        result = format_cost_table(reports)
        assert "s1" in result
        assert "bot" in result
        assert "0.0500" in result
