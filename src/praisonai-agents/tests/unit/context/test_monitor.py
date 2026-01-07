"""Tests for context monitor module."""

import tempfile
import os
from pathlib import Path


class TestContextMonitor:
    """Tests for ContextMonitor class."""
    
    def test_monitor_disabled_by_default(self):
        """Test monitor is disabled by default."""
        from praisonaiagents.context.monitor import ContextMonitor
        
        monitor = ContextMonitor()
        assert not monitor.enabled
    
    def test_monitor_enable_disable(self):
        """Test enable/disable methods."""
        from praisonaiagents.context.monitor import ContextMonitor
        
        monitor = ContextMonitor()
        
        monitor.enable()
        assert monitor.enabled
        
        monitor.disable()
        assert not monitor.enabled
    
    def test_should_write_when_disabled(self):
        """Test should_write returns False when disabled."""
        from praisonaiagents.context.monitor import ContextMonitor
        
        monitor = ContextMonitor(enabled=False)
        assert not monitor.should_write("turn")
        assert not monitor.should_write("manual")
    
    def test_should_write_frequency_turn(self):
        """Test should_write with turn frequency."""
        from praisonaiagents.context.monitor import ContextMonitor
        
        monitor = ContextMonitor(enabled=True, frequency="turn")
        
        assert monitor.should_write("turn")
        assert monitor.should_write("overflow")
        assert not monitor.should_write("tool_call")
    
    def test_should_write_frequency_tool_call(self):
        """Test should_write with tool_call frequency."""
        from praisonaiagents.context.monitor import ContextMonitor
        
        monitor = ContextMonitor(enabled=True, frequency="tool_call")
        
        assert monitor.should_write("tool_call")
        assert monitor.should_write("overflow")
    
    def test_should_write_frequency_manual(self):
        """Test should_write with manual frequency."""
        from praisonaiagents.context.monitor import ContextMonitor
        
        monitor = ContextMonitor(enabled=True, frequency="manual")
        
        assert monitor.should_write("manual")
        assert not monitor.should_write("turn")
    
    def test_snapshot_writes_file(self):
        """Test snapshot writes file to disk."""
        from praisonaiagents.context.monitor import ContextMonitor
        from praisonaiagents.context.models import ContextLedger, BudgetAllocation
        
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "context.txt")
            monitor = ContextMonitor(enabled=True, path=path)
            
            ledger = ContextLedger(history=1000, system_prompt=500)
            budget = BudgetAllocation()
            
            result_path = monitor.snapshot(
                ledger=ledger,
                budget=budget,
                messages=[{"role": "user", "content": "Hello"}],
                trigger="manual",
            )
            
            assert result_path is not None
            assert os.path.exists(path)
            
            content = Path(path).read_text()
            assert "PRAISONAI CONTEXT SNAPSHOT" in content
    
    def test_snapshot_json_format(self):
        """Test snapshot with JSON format."""
        from praisonaiagents.context.monitor import ContextMonitor
        from praisonaiagents.context.models import ContextLedger, BudgetAllocation
        import json
        
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "context.json")
            monitor = ContextMonitor(enabled=True, path=path, format="json")
            
            ledger = ContextLedger(history=1000)
            budget = BudgetAllocation()
            
            monitor.snapshot(
                ledger=ledger,
                budget=budget,
                messages=[],
                trigger="manual",
            )
            
            content = Path(path).read_text()
            data = json.loads(content)
            
            assert "ledger" in data
            assert "timestamp" in data
    
    def test_snapshot_not_written_when_disabled(self):
        """Test snapshot not written when disabled."""
        from praisonaiagents.context.monitor import ContextMonitor
        from praisonaiagents.context.models import ContextLedger, BudgetAllocation
        
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "context.txt")
            monitor = ContextMonitor(enabled=False, path=path)
            
            result = monitor.snapshot(
                ledger=ContextLedger(),
                budget=BudgetAllocation(),
                messages=[],
                trigger="turn",
            )
            
            assert result is None
            assert not os.path.exists(path)
    
    def test_set_path(self):
        """Test set_path method."""
        from praisonaiagents.context.monitor import ContextMonitor
        
        monitor = ContextMonitor()
        monitor.set_path("/new/path/context.txt")
        
        assert str(monitor.path) == "/new/path/context.txt"
    
    def test_set_format(self):
        """Test set_format method."""
        from praisonaiagents.context.monitor import ContextMonitor
        
        monitor = ContextMonitor(format="human")
        monitor.set_format("json")
        
        assert monitor.format == "json"
    
    def test_get_stats(self):
        """Test get_stats method."""
        from praisonaiagents.context.monitor import ContextMonitor
        
        monitor = ContextMonitor(enabled=True, path="./test.txt")
        stats = monitor.get_stats()
        
        assert "enabled" in stats
        assert "path" in stats
        assert "format" in stats
        assert stats["enabled"] is True


class TestRedaction:
    """Tests for sensitive data redaction."""
    
    def test_redact_api_key(self):
        """Test API key redaction."""
        from praisonaiagents.context.monitor import redact_sensitive
        
        text = "My API key is sk-proj-abc123def456ghi789jkl012mno345pqr678"
        result = redact_sensitive(text)
        
        assert "sk-proj-" not in result
        assert "[REDACTED]" in result
    
    def test_redact_password(self):
        """Test password redaction."""
        from praisonaiagents.context.monitor import redact_sensitive
        
        text = 'password: "mysecretpassword123"'
        result = redact_sensitive(text)
        
        assert "mysecretpassword" not in result
    
    def test_redact_preserves_normal_text(self):
        """Test normal text is preserved."""
        from praisonaiagents.context.monitor import redact_sensitive
        
        text = "Hello, how are you today?"
        result = redact_sensitive(text)
        
        assert result == text


class TestFormatting:
    """Tests for snapshot formatting."""
    
    def test_format_human_snapshot(self):
        """Test human-readable format."""
        from praisonaiagents.context.monitor import format_human_snapshot
        from praisonaiagents.context.models import ContextSnapshot, ContextLedger, BudgetAllocation
        
        snapshot = ContextSnapshot(
            timestamp="2025-01-07T12:00:00Z",
            session_id="test-session",
            agent_name="TestAgent",
            model_name="gpt-4o",
            budget=BudgetAllocation(),
            ledger=ContextLedger(history=5000, system_prompt=1000),
            utilization=0.5,
            warnings=["Test warning"],
        )
        
        result = format_human_snapshot(snapshot)
        
        assert "PRAISONAI CONTEXT SNAPSHOT" in result
        assert "TestAgent" in result
        assert "gpt-4o" in result
        assert "Test warning" in result
    
    def test_format_json_snapshot(self):
        """Test JSON format."""
        from praisonaiagents.context.monitor import format_json_snapshot
        from praisonaiagents.context.models import ContextSnapshot, ContextLedger, BudgetAllocation
        import json
        
        snapshot = ContextSnapshot(
            timestamp="2025-01-07T12:00:00Z",
            session_id="test-session",
            ledger=ContextLedger(),
            budget=BudgetAllocation(),
        )
        
        result = format_json_snapshot(snapshot)
        data = json.loads(result)
        
        assert data["timestamp"] == "2025-01-07T12:00:00Z"
        assert data["session_id"] == "test-session"


class TestMultiAgentMonitor:
    """Tests for MultiAgentMonitor class."""
    
    def test_get_agent_monitor(self):
        """Test getting agent-specific monitor."""
        from praisonaiagents.context.monitor import MultiAgentMonitor
        
        multi = MultiAgentMonitor(base_path="./context")
        
        monitor1 = multi.get_agent_monitor("agent1")
        monitor2 = multi.get_agent_monitor("agent2")
        
        assert monitor1 is not monitor2
        assert "agent1" in str(monitor1.path)
        assert "agent2" in str(monitor2.path)
    
    def test_enable_all(self):
        """Test enabling all monitors."""
        from praisonaiagents.context.monitor import MultiAgentMonitor
        
        multi = MultiAgentMonitor()
        multi.get_agent_monitor("agent1")
        multi.get_agent_monitor("agent2")
        
        multi.enable_all()
        
        assert multi.enabled
    
    def test_get_agent_ids(self):
        """Test getting list of agent IDs."""
        from praisonaiagents.context.monitor import MultiAgentMonitor
        
        multi = MultiAgentMonitor()
        multi.get_agent_monitor("agent1")
        multi.get_agent_monitor("agent2")
        
        ids = multi.get_agent_ids()
        
        assert "agent1" in ids
        assert "agent2" in ids
