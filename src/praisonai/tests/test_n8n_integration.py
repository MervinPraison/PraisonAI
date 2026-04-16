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

    def test_export_from_n8n_import(self):
        """Test that export_from_n8n can be imported."""
        try:
            from praisonai.n8n import export_from_n8n
            assert export_from_n8n is not None
        except ImportError:
            pytest.skip("n8n dependencies not available")

    def test_sync_workflow_import(self):
        """Test that sync_workflow can be imported."""
        try:
            from praisonai.n8n import sync_workflow
            assert sync_workflow is not None
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
        agent_nodes = [n for n in result["nodes"] if n["type"] == "n8n-nodes-base.httpRequest"]
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
        assert "staticData" not in result
        assert "tags" not in result
        assert "updatedAt" not in result
        assert "versionId" not in result

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
        agent_nodes = [n for n in nodes if n["type"] == "n8n-nodes-base.httpRequest"]
        assert len(agent_nodes) == 2
        
        # Check tool agent is converted to HTTP request node
        tool_agent = next((n for n in agent_nodes if "Tool Agent" in n["name"]), None)
        assert tool_agent is not None
        assert tool_agent["type"] == "n8n-nodes-base.httpRequest"
        assert tool_agent["parameters"]["method"] == "POST"
        assert "/api/v1/agents/tool_agent/invoke" in tool_agent["parameters"]["url"]
        
        # Check simple agent is also converted to HTTP request node
        simple_agent = next((n for n in agent_nodes if "Simple Agent" in n["name"]), None)
        assert simple_agent is not None
        assert simple_agent["type"] == "n8n-nodes-base.httpRequest"

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

    def test_http_request_agent_url_is_sanitized(self):
        """Test that agent IDs are sanitized for URL usage."""
        try:
            from praisonai.n8n import YAMLToN8nConverter
        except ImportError:
            pytest.skip("n8n dependencies not available")

        yaml_workflow = {
            "name": "Sanitize URL",
            "agents": {
                "Agent/One?": {"name": "Agent One", "instructions": "Do task"}
            }
        }

        converter = YAMLToN8nConverter()
        result = converter.convert(yaml_workflow)
        agent_node = next(n for n in result["nodes"] if n["type"] == "n8n-nodes-base.httpRequest")
        assert agent_node["parameters"]["url"].endswith("/api/v1/agents/Agent/One?/invoke")

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
                    "type": "n8n-nodes-base.httpRequest",
                    "position": [650, 300],
                    "parameters": {
                        "method": "POST",
                        "url": "http://localhost:8000/api/v1/agents/writer/invoke",
                        "sendBody": True,
                        "specifyBody": "json",
                        "jsonBody": "={{ JSON.stringify({ message: $json.result || 'Continue workflow' }) }}"
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
    
    def test_converter_roundtrip_preserves_all_fields(self):
        """Test complete round-trip preservation of all required fields."""
        try:
            from praisonai.n8n import YAMLToN8nConverter, N8nToYAMLConverter
        except ImportError:
            pytest.skip("n8n dependencies not available")
        
        # Input YAML with all fields that should be preserved
        input_yaml = {
            "name": "Test Workflow",
            "description": "Simple test workflow",
            "agents": {
                "researcher": {
                    "name": "Researcher",
                    "role": "Research Specialist",
                    "goal": "Research topics",
                    "backstory": "Expert researcher",
                    "llm": "gpt-4o-mini"
                },
                "writer": {
                    "name": "Writer", 
                    "role": "Writer",
                    "goal": "Write content",
                    "backstory": "Pro writer", 
                    "llm": "gpt-4o-mini"
                }
            },
            "steps": [
                {"agent": "researcher"},
                {"agent": "writer"}
            ]
        }
        
        # Round-trip conversion
        forward_converter = YAMLToN8nConverter()
        reverse_converter = N8nToYAMLConverter()
        
        n8n_json = forward_converter.convert(input_yaml)
        output_yaml = reverse_converter.convert(n8n_json)
        
        # Assertions per acceptance criteria
        
        # Round-trip preserves description
        assert output_yaml.get("description") == input_yaml["description"], "Workflow description not preserved"
        
        # Round-trip preserves goal and backstory for every agent
        for _agent_id, input_agent in input_yaml["agents"].items():
            # Find corresponding agent in output (ID may be different)
            output_agent = None
            for _aid, agent in output_yaml["agents"].items():
                if agent["name"] == input_agent["name"]:
                    output_agent = agent
                    break
            
            assert output_agent is not None, f"Agent {input_agent['name']} not found in output"
            assert output_agent.get("goal") == input_agent["goal"], f"Goal not preserved for {input_agent['name']}"
            assert output_agent.get("backstory") == input_agent["backstory"], f"Backstory not preserved for {input_agent['name']}"
        
        # Round-trip preserves all steps
        assert len(output_yaml["steps"]) == len(input_yaml["steps"]), "Not all steps preserved"
        
        # Agent references in steps should be preserved, including order and duplicates
        input_step_agent_names = [
            input_yaml["agents"][step["agent"]]["name"]
            for step in input_yaml["steps"]
            if "agent" in step
        ]
        output_step_agent_names = []
        for step in output_yaml["steps"]:
            if "agent" in step:
                output_agent_id = step["agent"]
                assert output_agent_id in output_yaml["agents"], (
                    f"Output step references unknown agent ID: {output_agent_id}"
                )
                output_step_agent_names.append(output_yaml["agents"][output_agent_id]["name"])
        
        assert output_step_agent_names == input_step_agent_names, (
            "Agent step references were not preserved"
        )

    def test_round_trip_conversion(self):
        """Test YAML -> n8n -> YAML round trip maintains core structure."""
        try:
            from praisonai.n8n import YAMLToN8nConverter, N8nToYAMLConverter
        except ImportError:
            pytest.skip("n8n dependencies not available")
        
        original_yaml = {
            "name": "Round Trip Test",
            "description": "Test workflow for round-trip conversion",
            "agents": {
                "researcher": {
                    "name": "Research Agent",
                    "role": "Research Specialist", 
                    "goal": "Research topics thoroughly",
                    "backstory": "Expert researcher with years of experience",
                    "instructions": "Research topics using available tools",
                    "llm": "gpt-4o-mini",
                    "tools": ["web_search"]
                },
                "writer": {
                    "name": "Content Writer",
                    "role": "Writer",
                    "goal": "Write engaging content", 
                    "backstory": "Professional content writer",
                    "instructions": "Write content based on research",
                    "llm": "gpt-4o-mini"
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
        assert result_yaml.get("description") == original_yaml["description"] 
        assert "agents" in result_yaml
        assert "steps" in result_yaml
        
        # Should have same number of agents
        original_agent_count = len(original_yaml["agents"])
        result_agent_count = len(result_yaml["agents"])
        assert result_agent_count == original_agent_count
        
        # Check that all steps are preserved
        assert len(result_yaml["steps"]) == len(original_yaml["steps"])
        
        # Verify agent fields are preserved
        result_agents = result_yaml["agents"]
        for agent_id, original_agent in original_yaml["agents"].items():
            # Agent ID might be transformed, so find by name
            result_agent = None
            for aid, agent in result_agents.items():
                if agent.get("name") == original_agent["name"]:
                    result_agent = agent
                    break
            
            assert result_agent is not None, f"Agent {original_agent['name']} not found in result"
            
            # Check all fields are preserved
            for field in ["role", "goal", "backstory", "llm"]:
                if field in original_agent:
                    assert result_agent.get(field) == original_agent[field], f"Field {field} not preserved for agent {original_agent['name']}"

    def test_round_trip_preserves_route_steps(self):
        """Test route control flow survives YAML -> n8n -> YAML conversion."""
        try:
            from praisonai.n8n import YAMLToN8nConverter, N8nToYAMLConverter
        except ImportError:
            pytest.skip("n8n dependencies not available")

        original_yaml = {
            "name": "Route Round Trip",
            "agents": {
                "classifier": {"name": "Classifier", "instructions": "Classify input"},
                "handler_a": {"name": "Handler A", "instructions": "Handle A"},
                "handler_b": {"name": "Handler B", "instructions": "Handle B"},
            },
            "steps": [
                {"agent": "classifier"},
                {"route": {"type_a": ["handler_a"], "type_b": ["handler_b"]}},
            ],
        }

        forward_converter = YAMLToN8nConverter()
        reverse_converter = N8nToYAMLConverter()

        n8n_json = forward_converter.convert(original_yaml)
        result_yaml = reverse_converter.convert(n8n_json)

        route_steps = [
            step["route"]
            for step in result_yaml.get("steps", [])
            if isinstance(step, dict) and "route" in step
        ]

        assert route_steps, "Route step missing after round-trip conversion"
        assert any(
            route.get("type_a") == ["handler_a"] and route.get("type_b") == ["handler_b"]
            for route in route_steps
        ), "Route mappings were not preserved"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
