#!/usr/bin/env python3
"""
Test agents.yaml field validation functionality.

This test verifies that the agents_generator properly validates agent configuration
field names and provides helpful suggestions for typos, as requested in issue #1628.
"""

import pytest
import logging
from unittest.mock import patch, MagicMock
import tempfile
import os
import yaml

def test_agents_yaml_typo_validation(caplog):
    """Test that unknown field names in agents.yaml produce warnings with suggestions."""
    # Import here to avoid import issues if dependencies are missing
    try:
        from praisonai.agents_generator import AgentsGenerator
    except ImportError:
        pytest.skip("AgentsGenerator not available - skipping validation test")
    
    # Create a temporary YAML file with a typo in field name
    yaml_content = {
        'framework': 'praisonai',
        'topic': 'Summarize Python history',
        'agents': {
            'researcher': {
                'role': 'Research Analyst',
                'goal': 'Provide a historical summary',
                'instrutions': 'Focus ONLY on years 1989–2000.',  # typo: should be 'instructions'
                'backstory': 'Expert researcher.'
            }
        }
    }
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        yaml.dump(yaml_content, f)
        yaml_file_path = f.name
    
    try:
        # Create AgentsGenerator with mocked dependencies to avoid import issues
        with patch('praisonai.agents_generator.PRAISONAI_TOOLS_AVAILABLE', False), \
             patch('praisonai.agents_generator.CREWAI_AVAILABLE', False), \
             patch('praisonai.agents_generator.AUTOGEN_AVAILABLE', False), \
             patch('praisonai.agents_generator.PRAISONAI_AVAILABLE', True), \
             patch('praisonai.agents_generator.AG2_AVAILABLE', False):
            
            # Mock the framework adapter to avoid dependency issues
            with patch.object(AgentsGenerator, '_get_framework_adapter') as mock_adapter:
                mock_framework = MagicMock()
                mock_framework.is_available.return_value = True
                mock_adapter.return_value = mock_framework
                
                generator = AgentsGenerator(
                    agent_file=yaml_file_path,
                    framework='praisonai',
                    config_list=[],
                    log_level=logging.DEBUG
                )
                
                # Set up logging to capture warnings
                with caplog.at_level(logging.WARNING):
                    # Call the validation method directly
                    with open(yaml_file_path, 'r') as f:
                        config = yaml.safe_load(f)
                    
                    generator._validate_agents_config(config)
        
        # Check that the warning was logged
        assert any("Unknown field 'instrutions' in agent 'researcher'" in record.message 
                  for record in caplog.records), "Expected warning about typo was not logged"
        
        # Check that a suggestion was provided
        assert any("Did you mean 'instructions'?" in record.message 
                  for record in caplog.records), "Expected suggestion was not logged"
    
    finally:
        # Clean up
        os.unlink(yaml_file_path)


def test_agents_yaml_valid_fields_no_warnings(caplog):
    """Test that valid field names don't produce warnings."""
    try:
        from praisonai.agents_generator import AgentsGenerator
    except ImportError:
        pytest.skip("AgentsGenerator not available - skipping validation test")
    
    # Create a temporary YAML file with valid field names
    yaml_content = {
        'framework': 'praisonai',
        'topic': 'Summarize Python history',
        'agents': {
            'researcher': {
                'role': 'Research Analyst',
                'goal': 'Provide a historical summary',
                'instructions': 'Focus ONLY on years 1989–2000.',  # correct field name
                'backstory': 'Expert researcher.',
                'tools': ['web_search'],
                'llm': 'gpt-4',
                'tool_timeout': 30
            }
        }
    }
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        yaml.dump(yaml_content, f)
        yaml_file_path = f.name
    
    try:
        with patch('praisonai.agents_generator.PRAISONAI_TOOLS_AVAILABLE', False), \
             patch('praisonai.agents_generator.CREWAI_AVAILABLE', False), \
             patch('praisonai.agents_generator.AUTOGEN_AVAILABLE', False), \
             patch('praisonai.agents_generator.PRAISONAI_AVAILABLE', True), \
             patch('praisonai.agents_generator.AG2_AVAILABLE', False):
            
            with patch.object(AgentsGenerator, '_get_framework_adapter') as mock_adapter:
                mock_framework = MagicMock()
                mock_framework.is_available.return_value = True
                mock_adapter.return_value = mock_framework
                
                generator = AgentsGenerator(
                    agent_file=yaml_file_path,
                    framework='praisonai',
                    config_list=[],
                    log_level=logging.DEBUG
                )
                
                with caplog.at_level(logging.WARNING):
                    with open(yaml_file_path, 'r') as f:
                        config = yaml.safe_load(f)
                    
                    generator._validate_agents_config(config)
        
        # Check that no warnings were logged for valid fields
        warnings = [record.message for record in caplog.records if record.levelno >= logging.WARNING]
        agent_field_warnings = [w for w in warnings if "Unknown field" in w and "researcher" in w]
        assert not agent_field_warnings, f"Unexpected warnings for valid fields: {agent_field_warnings}"
    
    finally:
        os.unlink(yaml_file_path)


def test_agents_yaml_unknown_field_no_close_match(caplog):
    """Test behavior when unknown field has no close matches."""
    try:
        from praisonai.agents_generator import AgentsGenerator
    except ImportError:
        pytest.skip("AgentsGenerator not available - skipping validation test")
    
    yaml_content = {
        'framework': 'praisonai',
        'topic': 'Test',
        'agents': {
            'test_agent': {
                'role': 'Tester',
                'goal': 'Test things',
                'xyz_random_field': 'some value'  # no close match expected
            }
        }
    }
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        yaml.dump(yaml_content, f)
        yaml_file_path = f.name
    
    try:
        with patch('praisonai.agents_generator.PRAISONAI_TOOLS_AVAILABLE', False), \
             patch('praisonai.agents_generator.CREWAI_AVAILABLE', False), \
             patch('praisonai.agents_generator.AUTOGEN_AVAILABLE', False), \
             patch('praisonai.agents_generator.PRAISONAI_AVAILABLE', True), \
             patch('praisonai.agents_generator.AG2_AVAILABLE', False):
            
            with patch.object(AgentsGenerator, '_get_framework_adapter') as mock_adapter:
                mock_framework = MagicMock()
                mock_framework.is_available.return_value = True
                mock_adapter.return_value = mock_framework
                
                generator = AgentsGenerator(
                    agent_file=yaml_file_path,
                    framework='praisonai',
                    config_list=[],
                    log_level=logging.DEBUG
                )
                
                with caplog.at_level(logging.WARNING):
                    with open(yaml_file_path, 'r') as f:
                        config = yaml.safe_load(f)
                    
                    generator._validate_agents_config(config)
        
        # Check that warning was logged but without suggestion
        warning_messages = [record.message for record in caplog.records if record.levelno >= logging.WARNING]
        unknown_field_warnings = [w for w in warning_messages if "Unknown field 'xyz_random_field'" in w]
        
        assert unknown_field_warnings, "Expected warning about unknown field was not logged"
        
        # Should not contain a suggestion since no close match
        suggestion_warnings = [w for w in unknown_field_warnings if "Did you mean" in w]
        assert not suggestion_warnings, f"Unexpected suggestion for field with no close match: {suggestion_warnings}"
    
    finally:
        os.unlink(yaml_file_path)


def test_roles_yaml_typo_validation(caplog):
    """Test that unknown field names in roles config produce warnings."""
    try:
        from praisonai.agents_generator import AgentsGenerator
    except ImportError:
        pytest.skip("AgentsGenerator not available - skipping validation test")

    yaml_content = {
        'framework': 'praisonai',
        'input': 'Test',
        'roles': {
            'researcher': {
                'role': 'Research Analyst',
                'goal': 'Provide a historical summary',
                'instrutions': 'Focus ONLY on years 1989–2000.'
            }
        }
    }

    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        yaml.dump(yaml_content, f)
        yaml_file_path = f.name

    try:
        with patch('praisonai.agents_generator.PRAISONAI_TOOLS_AVAILABLE', False), \
             patch('praisonai.agents_generator.CREWAI_AVAILABLE', False), \
             patch('praisonai.agents_generator.AUTOGEN_AVAILABLE', False), \
             patch('praisonai.agents_generator.PRAISONAI_AVAILABLE', True), \
             patch('praisonai.agents_generator.AG2_AVAILABLE', False):

            with patch.object(AgentsGenerator, '_get_framework_adapter') as mock_adapter:
                mock_framework = MagicMock()
                mock_framework.is_available.return_value = True
                mock_adapter.return_value = mock_framework

                generator = AgentsGenerator(
                    agent_file=yaml_file_path,
                    framework='praisonai',
                    config_list=[],
                    log_level=logging.DEBUG
                )

                with caplog.at_level(logging.WARNING):
                    with open(yaml_file_path, 'r') as f:
                        config = yaml.safe_load(f)

                    generator._validate_agents_config(config)

        assert any("Unknown field 'instrutions' in role 'researcher'" in record.message
                  for record in caplog.records), "Expected warning about typo in roles was not logged"
        assert any("Did you mean 'instructions'?" in record.message
                  for record in caplog.records), "Expected suggestion for roles typo was not logged"
    finally:
        os.unlink(yaml_file_path)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
