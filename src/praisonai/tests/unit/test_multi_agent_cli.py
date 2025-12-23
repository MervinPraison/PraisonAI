"""
Unit tests for Multi-Agent CLI feature.

Tests for:
- praisonai agents command with multiple --agent flags
- Agent definition parsing (name:role:tools format)
- Task execution with multiple agents
"""

import os
import sys
import tempfile
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
import argparse


class TestMultiAgentCLIArguments:
    """Tests for multi-agent CLI argument parsing."""
    
    def test_agents_command_recognized(self):
        """Test that 'agents' is a recognized command."""
        # Just verify the agents module loads without error
        from praisonai.cli.features.agents import MultiAgentHandler, parse_agent_definition
        assert MultiAgentHandler is not None
        assert parse_agent_definition is not None
    
    def test_agent_argument_parsing(self):
        """Test --agent argument can be used multiple times."""
        from praisonai.cli.features.agents import add_agents_parser
        
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers(dest='agents_command')
        add_agents_parser(subparsers)
        
        args = parser.parse_args([
            'run',
            '--agent', 'researcher:Research Analyst:internet_search',
            '--agent', 'writer:Content Writer:write_file',
            '--task', 'Research AI trends and write a report'
        ])
        
        assert len(args.agent) == 2
        assert args.task == 'Research AI trends and write a report'
    
    def test_agent_with_instructions(self):
        """Test --agent with instructions."""
        from praisonai.cli.features.agents import add_agents_parser
        
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers(dest='agents_command')
        add_agents_parser(subparsers)
        
        args = parser.parse_args([
            'run',
            '--agent', 'analyst:Data Analyst:read_csv,analyze_csv',
            '--instructions', 'Be thorough and accurate',
            '--task', 'Analyze the sales data'
        ])
        
        assert args.instructions == 'Be thorough and accurate'
    
    def test_agent_with_llm(self):
        """Test --llm argument for model selection."""
        from praisonai.cli.features.agents import add_agents_parser
        
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers(dest='agents_command')
        add_agents_parser(subparsers)
        
        args = parser.parse_args([
            'run',
            '--agent', 'coder:Developer:execute_command',
            '--llm', 'gpt-4o',
            '--task', 'Write a Python script'
        ])
        
        assert args.llm == 'gpt-4o'


class TestAgentDefinitionParsing:
    """Tests for parsing agent definitions."""
    
    def test_parse_agent_definition_basic(self):
        """Test parsing basic agent definition."""
        from praisonai.cli.features.agents import parse_agent_definition
        
        result = parse_agent_definition("researcher:Research Analyst:internet_search")
        
        assert result['name'] == 'researcher'
        assert result['role'] == 'Research Analyst'
        assert result['tools'] == ['internet_search']
    
    def test_parse_agent_definition_multiple_tools(self):
        """Test parsing agent with multiple tools."""
        from praisonai.cli.features.agents import parse_agent_definition
        
        result = parse_agent_definition("analyst:Data Analyst:read_csv,write_csv,analyze_csv")
        
        assert result['name'] == 'analyst'
        assert result['role'] == 'Data Analyst'
        assert result['tools'] == ['read_csv', 'write_csv', 'analyze_csv']
    
    def test_parse_agent_definition_no_tools(self):
        """Test parsing agent without tools."""
        from praisonai.cli.features.agents import parse_agent_definition
        
        result = parse_agent_definition("helper:Assistant")
        
        assert result['name'] == 'helper'
        assert result['role'] == 'Assistant'
        assert result['tools'] == []
    
    def test_parse_agent_definition_with_goal(self):
        """Test parsing agent with goal (extended format)."""
        from praisonai.cli.features.agents import parse_agent_definition
        
        # Extended format: name:role:tools:goal
        result = parse_agent_definition("writer:Writer:write_file:Create high-quality content")
        
        assert result['name'] == 'writer'
        assert result['role'] == 'Writer'
        assert result['tools'] == ['write_file']
        assert result.get('goal') == 'Create high-quality content'


class TestMultiAgentHandler:
    """Tests for MultiAgentHandler class."""
    
    def test_handler_initialization(self):
        """Test handler initializes correctly."""
        from praisonai.cli.features.agents import MultiAgentHandler
        
        handler = MultiAgentHandler(verbose=False)
        assert handler is not None
    
    def test_create_agents_from_definitions(self):
        """Test creating agents from definition strings."""
        from praisonai.cli.features.agents import MultiAgentHandler
        
        handler = MultiAgentHandler(verbose=False)
        
        definitions = [
            "researcher:Research Analyst:internet_search",
            "writer:Content Writer:write_file"
        ]
        
        agents = handler.create_agents_from_definitions(definitions)
        
        assert len(agents) == 2
        assert agents[0]['name'] == 'researcher'
        assert agents[1]['name'] == 'writer'
    
    def test_run_with_mock_agents(self):
        """Test running multi-agent task with mocked agents."""
        from praisonai.cli.features.agents import MultiAgentHandler
        
        handler = MultiAgentHandler(verbose=False)
        
        with patch.object(handler, '_execute_agents') as mock_execute:
            mock_execute.return_value = "Task completed successfully"
            
            result = handler.run(
                agent_definitions=[
                    "researcher:Researcher:internet_search"
                ],
                task="Find information about AI"
            )
            
            # Should have called execute
            mock_execute.assert_called_once()


class TestMultiAgentExecution:
    """Tests for multi-agent execution."""
    
    def test_sequential_execution(self):
        """Test agents execute sequentially by default."""
        from praisonai.cli.features.agents import MultiAgentHandler
        
        handler = MultiAgentHandler(verbose=False)
        
        # This tests the configuration, not actual execution
        config = handler.prepare_execution_config(
            agent_definitions=[
                "agent1:Role1:tool1",
                "agent2:Role2:tool2"
            ],
            task="Test task",
            process="sequential"
        )
        
        assert config['process'] == 'sequential'
        assert len(config['agents']) == 2
    
    def test_parallel_execution_option(self):
        """Test parallel execution option."""
        from praisonai.cli.features.agents import MultiAgentHandler
        
        handler = MultiAgentHandler(verbose=False)
        
        config = handler.prepare_execution_config(
            agent_definitions=[
                "agent1:Role1:tool1",
                "agent2:Role2:tool2"
            ],
            task="Test task",
            process="parallel"
        )
        
        assert config['process'] == 'parallel'


class TestAgentsCLIIntegration:
    """Integration tests for agents CLI."""
    
    def test_help_command(self):
        """Test agents --help works."""
        from praisonai.cli.features.agents import add_agents_parser
        
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers(dest='agents_command')
        add_agents_parser(subparsers)
        
        # Should not raise
        with pytest.raises(SystemExit) as exc_info:
            parser.parse_args(['run', '--help'])
        assert exc_info.value.code == 0
    
    def test_missing_task_error(self):
        """Test error when task is missing."""
        from praisonai.cli.features.agents import add_agents_parser
        
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers(dest='agents_command')
        add_agents_parser(subparsers)
        
        # Should fail without --task
        with pytest.raises(SystemExit):
            parser.parse_args([
                'run',
                '--agent', 'test:Tester:test_tool'
            ])
