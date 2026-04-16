"""
Tests for n8n integration functionality.

Tests the new n8n package for bidirectional conversion between PraisonAI YAML
workflows and n8n JSON format for visual editing.
"""

import pytest
import json
import os
import tempfile
import yaml
from pathlib import Path


class TestN8nConverter:
    """Tests for YAML to n8n JSON conversion."""
    
    @pytest.fixture
    def sample_agents_yaml_dict(self):
        """Sample agents YAML as dictionary for testing."""
        return {
            "name": "Test Research Workflow",
            "agents": {
                "researcher": {
                    "name": "Research Agent",
                    "role": "Research Analyst",
                    "instructions": "Research topics thoroughly using web search",
                    "tools": ["tavily_search", "web_search"],
                    "llm": "gpt-4o-mini"
                },
                "writer": {
                    "name": "Content Writer",
                    "role": "Writer",
                    "instructions": "Write engaging content based on research",
                    "llm": "gpt-4o-mini"
                }
            },
            "steps": [
                {"agent": "researcher"},
                {"agent": "writer"}
            ]
        }

    @pytest.fixture
    def sample_yaml_file(self, sample_agents_yaml_dict):
        """Create a temporary YAML file for testing."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(sample_agents_yaml_dict, f, default_flow_style=False)
            f.flush()
            yield f.name
        os.unlink(f.name)

    def test_yaml_to_n8n_converter_import(self):
        """Test that YAMLToN8nConverter can be imported."""
        try:
            from praisonai.n8n import YAMLToN8nConverter
            assert YAMLToN8nConverter is not None
        except ImportError:
            pytest.skip("n8n dependencies not available")

    def test_n8n_to_yaml_converter_import(self):
        """Test that N8nToYAMLConverter can be imported."""
        try:
            from praisonai.n8n import N8nToYAMLConverter
            assert N8nToYAMLConverter is not None
        except ImportError:
            pytest.skip("n8n dependencies not available")

    def test_n8n_client_import(self):
        """Test that N8nClient can be imported."""
        try:
            from praisonai.n8n import N8nClient
            assert N8nClient is not None
        except ImportError:
            pytest.skip("n8n dependencies not available")

    def test_preview_workflow_import(self):
        """Test that preview_workflow can be imported."""
        try:
            from praisonai.n8n import preview_workflow
            assert preview_workflow is not None
        except ImportError:
            pytest.skip("n8n dependencies not available")

    def test_yaml_to_n8n_conversion(self, sample_agents_yaml_dict):
        """Test basic YAML to n8n conversion."""
        try:
            from praisonai.n8n import YAMLToN8nConverter
        except ImportError:
            pytest.skip("n8n dependencies not available")
        
        converter = YAMLToN8nConverter()
        result = converter.convert(sample_agents_yaml_dict)
        
        # Check basic structure
        assert "name" in result
        assert "nodes" in result
        assert "connections" in result
        assert "settings" in result
        
        # Check workflow name
        assert result["name"] == "Test Research Workflow"
        
        # Check nodes count (trigger + 2 agents)
        assert len(result["nodes"]) == 3
        
        # Check trigger node exists
        trigger_nodes = [n for n in result["nodes"] if n["type"] == "n8n-nodes-base.manualTrigger"]
        assert len(trigger_nodes) == 1
        
        # Check agent nodes
        agent_nodes = [n for n in result["nodes"] if "langchain" in n["type"]]
        assert len(agent_nodes) == 2

    def test_n8n_workflow_has_required_keys(self, sample_agents_yaml_dict):
        """Test that n8n workflow JSON has required keys."""
        try:
            from praisonai.n8n import YAMLToN8nConverter
        except ImportError:
            pytest.skip("n8n dependencies not available")
            
        converter = YAMLToN8nConverter()
        result = converter.convert(sample_agents_yaml_dict)
        
        assert "name" in result
        assert "nodes" in result
        assert "connections" in result
        assert "settings" in result
        assert "staticData" in result
        assert "tags" in result

    def test_agent_node_mapping(self):
        """Test that agents are correctly mapped to n8n nodes."""
        try:
            from praisonai.n8n import YAMLToN8nConverter
        except ImportError:
            pytest.skip("n8n dependencies not available")
        
        yaml_workflow = {
            "name": "Agent Test",
            "agents": {
                "tool_agent": {
                    "name": "Tool Agent",
                    "instructions": "Use tools to help",
                    "tools": ["web_search"]
                },
                "simple_agent": {
                    "name": "Simple Agent", 
                    "instructions": "Just chat"
                }
            }
        }
        
        converter = YAMLToN8nConverter()
        result = converter.convert(yaml_workflow)
        
        nodes = result["nodes"]
        
        # Find agent nodes (exclude trigger)
        agent_nodes = [n for n in nodes if "langchain" in n["type"]]
        assert len(agent_nodes) == 2
        
        # Check tool agent uses agent type
        tool_agent = next((n for n in agent_nodes if "Tool Agent" in n["name"]), None)
        assert tool_agent is not None
        assert tool_agent["type"] == "@n8n/n8n-nodes-langchain.agent"
        
        # Check simple agent uses chain LLM type
        simple_agent = next((n for n in agent_nodes if "Simple Agent" in n["name"]), None)
        assert simple_agent is not None
        assert simple_agent["type"] == "@n8n/n8n-nodes-langchain.chainLlm"

    def test_tool_conversion(self):
        """Test that tools are correctly converted."""
        try:
            from praisonai.n8n.converter import YAMLToN8nConverter
        except ImportError:
            pytest.skip("n8n dependencies not available")
        
        converter = YAMLToN8nConverter()
        
        # Test common tool mappings
        tools = ["tavily_search", "web_search", "python_exec", "file_read"]
        converted = converter._convert_tools(tools)
        
        assert len(converted) == 4
        assert any(t["type"] == "web_search" for t in converted)
        assert any(t["type"] == "code_execution" for t in converted)
        assert any(t["type"] == "file_operations" for t in converted)

    def test_node_positions_are_sequential(self, sample_agents_yaml_dict):
        """Test that node positions are laid out sequentially."""
        try:
            from praisonai.n8n import YAMLToN8nConverter
        except ImportError:
            pytest.skip("n8n dependencies not available")
            
        converter = YAMLToN8nConverter()
        result = converter.convert(sample_agents_yaml_dict)
        
        nodes = result["nodes"]
        positions = [n.get("position", [0, 0]) for n in nodes]
        
        # X positions should increase for sequential workflow
        x_positions = [p[0] for p in positions]
        assert x_positions == sorted(x_positions), "Nodes should be positioned left to right"


class TestN8nReverseConverter:
    """Tests for n8n JSON to YAML conversion."""
    
    @pytest.fixture
    def sample_n8n_workflow(self):
        """Sample n8n workflow JSON for testing."""
        return {
            "name": "Test Research Workflow",
            "nodes": [
                {
                    "name": "Manual Trigger",
                    "type": "n8n-nodes-base.manualTrigger",
                    "position": [250, 300],
                    "parameters": {}
                },
                {
                    "name": "Research Agent",
                    "type": "@n8n/n8n-nodes-langchain.agent",
                    "position": [450, 300],
                    "parameters": {
                        "options": {
                            "systemMessage": "Research topics thoroughly using web search",
                            "role": "Research Analyst",
                            "model": "gpt-4o-mini"
                        },
                        "tools": [
                            {"type": "web_search", "name": "Web Search"}
                        ]
                    }
                },
                {
                    "name": "Content Writer",
                    "type": "@n8n/n8n-nodes-langchain.chainLlm",
                    "position": [650, 300],
                    "parameters": {
                        "options": {
                            "systemMessage": "Write engaging content based on research",
                            "role": "Writer",
                            "model": "gpt-4o-mini"
                        }
                    }
                }
            ],
            "connections": {
                "Manual Trigger": {
                    "main": [[{"node": "Research Agent", "type": "main", "index": 0}]]
                },
                "Research Agent": {
                    "main": [[{"node": "Content Writer", "type": "main", "index": 0}]]
                }
            },
            "settings": {"executionOrder": "v1"}
        }

    def test_n8n_to_yaml_conversion(self, sample_n8n_workflow):
        """Test basic n8n to YAML conversion."""
        try:
            from praisonai.n8n import N8nToYAMLConverter
        except ImportError:
            pytest.skip("n8n dependencies not available")
        
        converter = N8nToYAMLConverter()
        result = converter.convert(sample_n8n_workflow)
        
        # Check basic structure
        assert "name" in result
        assert "agents" in result
        assert "steps" in result
        
        # Check workflow name
        assert result["name"] == "Test Research Workflow"
        
        # Check agents converted
        assert len(result["agents"]) == 2


class TestN8nClient:
    """Tests for N8nClient API integration."""

    def test_n8n_client_initialization(self):
        """Test N8nClient can be initialized."""
        try:
            from praisonai.n8n import N8nClient
        except ImportError:
            pytest.skip("n8n dependencies not available")
        
        # Test default initialization
        client = N8nClient()
        assert client.base_url == "http://localhost:5678"
        assert client.api_key is None
        
        # Test custom initialization
        client = N8nClient(base_url="http://example.com:8080", api_key="test-key")
        assert client.base_url == "http://example.com:8080"
        assert client.api_key == "test-key"
        
        client.close()


class TestN8nCLIIntegration:
    """Tests for CLI integration of n8n feature."""
    
    def test_cli_command_structure(self):
        """Test that CLI commands are properly structured."""
        try:
            from praisonai.cli.commands.n8n import app
        except ImportError:
            pytest.skip("CLI commands not available")
        
        # Check that the main app is a typer app
        assert hasattr(app, 'commands')
        
        # Check that expected commands exist
        command_names = [cmd.name for cmd in app.commands.values()]
        expected_commands = ['export', 'import', 'preview', 'push', 'pull', 'test', 'list']
        
        for cmd in expected_commands:
            assert cmd in command_names, f"Command '{cmd}' not found in CLI app"

    def test_execute_method_exists(self):
        """Test that CLI commands have proper structure."""
        try:
            from praisonai.cli.commands.n8n import export, preview
        except ImportError:
            pytest.skip("CLI commands not available")
        
        # Commands should be callable functions
        assert callable(export)
        assert callable(preview)


class TestN8nWorkflowPatterns:
    """Tests for different workflow patterns."""
    
    def test_parallel_workflow_conversion(self):
        """Test that parallel steps are handled correctly."""
        try:
            from praisonai.n8n import YAMLToN8nConverter
        except ImportError:
            pytest.skip("n8n dependencies not available")
        
        parallel_workflow = {
            "name": "Parallel Workflow",
            "agents": {
                "agent1": {
                    "name": "Agent1",
                    "instructions": "Do task 1"
                },
                "agent2": {
                    "name": "Agent2", 
                    "instructions": "Do task 2"
                }
            },
            "steps": [
                {
                    "parallel": [
                        {"agent": "agent1"},
                        {"agent": "agent2"}
                    ]
                }
            ]
        }
        
        converter = YAMLToN8nConverter()
        result = converter.convert(parallel_workflow)
        
        # Should have nodes for parallel execution
        assert len(result["nodes"]) >= 3  # trigger + 2 agents

    def test_route_workflow_conversion(self):
        """Test that route steps are handled correctly."""
        try:
            from praisonai.n8n import YAMLToN8nConverter
        except ImportError:
            pytest.skip("n8n dependencies not available")
        
        route_workflow = {
            "name": "Route Workflow",
            "agents": {
                "classifier": {
                    "name": "Classifier",
                    "instructions": "Classify the input"
                },
                "handler_a": {
                    "name": "Handler A",
                    "instructions": "Handle type A"
                },
                "handler_b": {
                    "name": "Handler B",
                    "instructions": "Handle type B"
                }
            },
            "steps": [
                {"agent": "classifier"},
                {
                    "route": {
                        "type_a": ["handler_a"],
                        "type_b": ["handler_b"]
                    }
                }
            ]
        }
        
        converter = YAMLToN8nConverter()
        result = converter.convert(route_workflow)
        
        # Should have nodes including a switch node for routing
        assert len(result["nodes"]) >= 4  # trigger + classifier + router + handlers
        
        # Should have switch node for routing
        switch_nodes = [n for n in result["nodes"] if "switch" in n["type"]]
        assert len(switch_nodes) >= 1


class TestN8nRoundTrip:
    """Tests for round-trip conversion."""

    def test_round_trip_conversion(self):
        """Test YAML -> n8n -> YAML round trip maintains core structure."""
        try:
            from praisonai.n8n import YAMLToN8nConverter, N8nToYAMLConverter
        except ImportError:
            pytest.skip("n8n dependencies not available")
        
        original_yaml = {
            "name": "Round Trip Test",
            "agents": {
                "researcher": {
                    "name": "Research Agent",
                    "instructions": "Research topics",
                    "tools": ["web_search"]
                },
                "writer": {
                    "name": "Content Writer",
                    "instructions": "Write content"
                }
            },
            "steps": [
                {"agent": "researcher"},
                {"agent": "writer"}
            ]
        }
        
        # Convert YAML to n8n
        yaml_converter = YAMLToN8nConverter()
        n8n_workflow = yaml_converter.convert(original_yaml)
        
        # Convert back to YAML
        n8n_converter = N8nToYAMLConverter()
        result_yaml = n8n_converter.convert(n8n_workflow)
        
        # Check that core structure is preserved
        assert result_yaml["name"] == original_yaml["name"]
        assert "agents" in result_yaml
        assert "steps" in result_yaml
        
        # Should have same number of agents (within reason - conversion may change names)
        original_agent_count = len(original_yaml["agents"])
        result_agent_count = len(result_yaml["agents"])
        assert result_agent_count == original_agent_count


if __name__ == "__main__":
    pytest.main([__file__, "-v"])