"""
Test default values for scheduler, especially max_cost safety default.
"""
import pytest
from unittest.mock import Mock
from praisonai.scheduler import AgentScheduler


class TestSchedulerDefaults:
    """Test default values in AgentScheduler."""
    
    def test_default_max_cost_is_one_dollar(self):
        """Test that default max_cost is $1.00 for safety."""
        mock_agent = Mock()
        mock_agent.name = "Test Agent"
        
        scheduler = AgentScheduler(
            agent=mock_agent,
            task="Test task"
        )
        
        assert scheduler.max_cost == 1.00, "Default max_cost should be $1.00"
    
    def test_explicit_max_cost_overrides_default(self):
        """Test that explicit max_cost overrides the default."""
        mock_agent = Mock()
        mock_agent.name = "Test Agent"
        
        scheduler = AgentScheduler(
            agent=mock_agent,
            task="Test task",
            max_cost=5.00
        )
        
        assert scheduler.max_cost == 5.00, "Explicit max_cost should override default"
    
    def test_none_max_cost_disables_limit(self):
        """Test that max_cost=None disables budget limit."""
        mock_agent = Mock()
        mock_agent.name = "Test Agent"
        
        scheduler = AgentScheduler(
            agent=mock_agent,
            task="Test task",
            max_cost=None
        )
        
        assert scheduler.max_cost is None, "max_cost=None should disable limit"
    
    def test_yaml_loader_applies_default_max_cost(self):
        """Test that YAML loader applies $1.00 default when not specified."""
        from praisonai.scheduler.yaml_loader import load_agent_yaml_with_schedule
        import tempfile
        import os
        
        yaml_content = """
framework: praisonai

agents:
  - name: "Test Agent"
    role: "Tester"
    instructions: "Test instructions"

task: "Test task"

schedule:
  interval: "hourly"
"""
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(yaml_content)
            temp_path = f.name
        
        try:
            agent_config, schedule_config = load_agent_yaml_with_schedule(temp_path)
            assert schedule_config['max_cost'] == 1.00, "YAML loader should apply $1.00 default"
        finally:
            os.unlink(temp_path)
    
    def test_yaml_explicit_max_cost_overrides_default(self):
        """Test that explicit max_cost in YAML overrides default."""
        from praisonai.scheduler.yaml_loader import load_agent_yaml_with_schedule
        import tempfile
        import os
        
        yaml_content = """
framework: praisonai

agents:
  - name: "Test Agent"
    role: "Tester"
    instructions: "Test instructions"

task: "Test task"

schedule:
  interval: "hourly"
  max_cost: 5.00
"""
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(yaml_content)
            temp_path = f.name
        
        try:
            agent_config, schedule_config = load_agent_yaml_with_schedule(temp_path)
            assert schedule_config['max_cost'] == 5.00, "Explicit YAML max_cost should override default"
        finally:
            os.unlink(temp_path)
    
    def test_scheduler_stops_at_budget_limit(self):
        """Test that scheduler stops when budget limit is reached."""
        mock_agent = Mock()
        mock_agent.name = "Test Agent"
        
        scheduler = AgentScheduler(
            agent=mock_agent,
            task="Test task",
            max_cost=0.0003  # Very low limit for testing
        )
        
        # Simulate cost accumulation
        scheduler._total_cost = 0.0003
        
        # Check that budget is reached
        assert scheduler._total_cost >= scheduler.max_cost, "Budget should be reached"
    
    def test_default_timeout_is_none(self):
        """Test that default timeout is None (no limit)."""
        mock_agent = Mock()
        mock_agent.name = "Test Agent"
        
        scheduler = AgentScheduler(
            agent=mock_agent,
            task="Test task"
        )
        
        assert scheduler.timeout is None, "Default timeout should be None"
    
    def test_stats_include_cost_tracking(self):
        """Test that get_stats includes cost tracking."""
        mock_agent = Mock()
        mock_agent.name = "Test Agent"
        
        scheduler = AgentScheduler(
            agent=mock_agent,
            task="Test task"
        )
        
        stats = scheduler.get_stats()
        
        assert 'total_cost_usd' in stats, "Stats should include total_cost_usd"
        assert 'cost_per_execution' in stats, "Stats should include cost_per_execution"
        assert stats['total_cost_usd'] == 0.0, "Initial cost should be 0"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
