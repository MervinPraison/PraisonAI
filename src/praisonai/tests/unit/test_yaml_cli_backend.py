"""Unit tests for YAML CLI backend parsing."""

import pytest
import yaml
from unittest.mock import patch, MagicMock

def test_yaml_cli_backend_string():
    """Test YAML parsing with string CLI backend."""
    yaml_content = """
framework: praisonai
topic: coding
roles:
  coder:
    role: Code refactorer
    goal: Refactor Python modules
    backstory: Senior engineer
    cli_backend: claude-code
    tasks:
      refactor:
        description: Refactor utils.py
        expected_output: Refactored code
"""
    
    from praisonai.agents_generator import AgentsGenerator
    
    with patch('praisonai.cli_backends.resolve_cli_backend') as mock_resolve:
        mock_backend = MagicMock()
        mock_resolve.return_value = mock_backend
        
        generator = AgentsGenerator(config=yaml_content)
        agents, _tasks = generator.create_agents_and_tasks()
        
        # Verify agent was created with CLI backend
        assert 'coder' in agents
        agent = agents['coder']
        assert getattr(agent, '_cli_backend', None) is mock_backend
        
        # Verify CLI backend was resolved correctly
        mock_resolve.assert_called_once_with('claude-code')

def test_yaml_cli_backend_dict():
    """Test YAML parsing with dict CLI backend configuration."""
    yaml_content = """
framework: praisonai
topic: coding
roles:
  coder:
    role: Code refactorer
    goal: Refactor Python modules
    backstory: Senior engineer
    cli_backend:
      id: claude-code
      overrides:
        timeout_ms: 60000
    tasks:
      refactor:
        description: Refactor utils.py
        expected_output: Refactored code
"""
    
    from praisonai.agents_generator import AgentsGenerator
    
    with patch('praisonai.cli_backends.resolve_cli_backend') as mock_resolve:
        mock_backend = MagicMock()
        mock_resolve.return_value = mock_backend
        
        generator = AgentsGenerator(config=yaml_content)
        agents, _tasks = generator.create_agents_and_tasks()
        
        # Verify agent was created with CLI backend
        assert 'coder' in agents
        agent = agents['coder']
        assert getattr(agent, '_cli_backend', None) is mock_backend
        
        # Verify CLI backend was resolved with overrides
        mock_resolve.assert_called_once_with('claude-code', overrides={'timeout_ms': 60000})

def test_yaml_cli_backend_dict_missing_id():
    """Test YAML parsing with invalid dict CLI backend (missing id)."""
    yaml_content = """
framework: praisonai
topic: coding
roles:
  coder:
    role: Code refactorer
    goal: Refactor Python modules
    backstory: Senior engineer
    cli_backend:
      overrides:
        timeout_ms: 60000
    tasks:
      refactor:
        description: Refactor utils.py
        expected_output: Refactored code
"""
    
    from praisonai.agents_generator import AgentsGenerator
    
    # Should not raise exception but log warning
    generator = AgentsGenerator(config=yaml_content)
    agents, _tasks = generator.create_agents_and_tasks()
    
    # Agent should be created without CLI backend
    assert 'coder' in agents
    agent = agents['coder']
    # Agent should not have cli_backend set due to invalid config
    assert not hasattr(agent, '_cli_backend') or agent._cli_backend is None

def test_yaml_no_cli_backend():
    """Test YAML parsing without CLI backend."""
    yaml_content = """
framework: praisonai
topic: coding
roles:
  coder:
    role: Code refactorer
    goal: Refactor Python modules
    backstory: Senior engineer
    tasks:
      refactor:
        description: Refactor utils.py
        expected_output: Refactored code
"""
    
    from praisonai.agents_generator import AgentsGenerator
    
    generator = AgentsGenerator(config=yaml_content)
    agents, _tasks = generator.create_agents_and_tasks()
    
    # Verify agent was created without CLI backend
    assert 'coder' in agents
    agent = agents['coder']
    assert not hasattr(agent, '_cli_backend') or agent._cli_backend is None

def test_yaml_cli_backend_import_error():
    """Test YAML parsing with CLI backend when import fails."""
    yaml_content = """
framework: praisonai
topic: coding
roles:
  coder:
    role: Code refactorer
    goal: Refactor Python modules
    backstory: Senior engineer
    cli_backend: claude-code
    tasks:
      refactor:
        description: Refactor utils.py
        expected_output: Refactored code
"""
    
    from praisonai.agents_generator import AgentsGenerator
    
    with patch('praisonai.cli_backends.resolve_cli_backend', side_effect=ImportError("CLI backends not available")):
        generator = AgentsGenerator(config=yaml_content)
        agents, _tasks = generator.create_agents_and_tasks()
        
        # Agent should be created without CLI backend due to import error
        assert 'coder' in agents
        agent = agents['coder']
        assert not hasattr(agent, '_cli_backend') or agent._cli_backend is None

def test_yaml_cli_backend_invalid_type():
    """Test YAML parsing with invalid CLI backend type."""
    yaml_content = """
framework: praisonai
topic: coding
roles:
  coder:
    role: Code refactorer
    goal: Refactor Python modules
    backstory: Senior engineer
    cli_backend: 123
    tasks:
      refactor:
        description: Refactor utils.py
        expected_output: Refactored code
"""
    
    from praisonai.agents_generator import AgentsGenerator
    
    # Should not raise exception but log warning
    generator = AgentsGenerator(config=yaml_content)
    agents, _tasks = generator.create_agents_and_tasks()
    
    # Agent should be created without CLI backend due to invalid type
    assert 'coder' in agents
    agent = agents['coder']
    assert not hasattr(agent, '_cli_backend') or agent._cli_backend is None