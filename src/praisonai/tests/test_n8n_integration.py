"""
Test-Driven Development tests for n8n integration.

Tests for converting PraisonAI agents.yaml to n8n workflow JSON format.
"""

import pytest
import json
import os
import tempfile
from pathlib import Path


class TestN8nConverter:
    """Tests for YAML to n8n JSON conversion."""
    
    @pytest.fixture
    def sample_agents_yaml(self):
        """Sample agents.yaml content for testing."""
        return """
name: Test Workflow
description: A test workflow for n8n integration

agents:
  researcher:
    name: Researcher
    role: Research Analyst
    goal: Research topics
    instructions: Research and gather information

  writer:
    name: Writer
    role: Content Writer
    goal: Write content
    instructions: Write based on research

steps:
  - agent: researcher
    action: "Research the topic"
  
  - agent: writer
    action: "Write content based on research"
"""

    @pytest.fixture
    def sample_yaml_file(self, sample_agents_yaml):
        """Create a temporary YAML file for testing."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(sample_agents_yaml)
            f.flush()
            yield f.name
        os.unlink(f.name)

    def test_n8n_handler_import(self):
        """Test that N8nHandler can be imported."""
        from praisonai.cli.features.n8n import N8nHandler
        assert N8nHandler is not None

    def test_n8n_handler_initialization(self):
        """Test N8nHandler initialization."""
        from praisonai.cli.features.n8n import N8nHandler
        handler = N8nHandler(verbose=True)
        assert handler.feature_name == "n8n"
        assert handler.verbose is True

    def test_convert_yaml_to_n8n_returns_dict(self, sample_yaml_file):
        """Test that convert_yaml_to_n8n returns a dictionary."""
        from praisonai.cli.features.n8n import N8nHandler
        handler = N8nHandler()
        result = handler.convert_yaml_to_n8n(sample_yaml_file)
        assert isinstance(result, dict)

    def test_n8n_workflow_has_required_keys(self, sample_yaml_file):
        """Test that n8n workflow JSON has required keys."""
        from praisonai.cli.features.n8n import N8nHandler
        handler = N8nHandler()
        result = handler.convert_yaml_to_n8n(sample_yaml_file)
        
        assert "name" in result
        assert "nodes" in result
        assert "connections" in result

    def test_n8n_workflow_has_trigger_node(self, sample_yaml_file):
        """Test that n8n workflow has a trigger node (webhook or manual)."""
        from praisonai.cli.features.n8n import N8nHandler
        handler = N8nHandler()
        result = handler.convert_yaml_to_n8n(sample_yaml_file)
        
        nodes = result["nodes"]
        # Check for webhook or manual trigger nodes
        trigger_nodes = [n for n in nodes if "trigger" in n.get("type", "").lower() 
                        or "webhook" in n.get("type", "").lower()
                        or "trigger" in n.get("name", "").lower()
                        or "webhook" in n.get("name", "").lower()]
        assert len(trigger_nodes) >= 1

    def test_n8n_workflow_has_per_agent_nodes(self, sample_yaml_file):
        """Test that n8n workflow has HTTP Request nodes for each agent."""
        from praisonai.cli.features.n8n import N8nHandler
        handler = N8nHandler()
        result = handler.convert_yaml_to_n8n(sample_yaml_file)
        
        nodes = result["nodes"]
        # Should have HTTP Request nodes for each agent
        http_nodes = [n for n in nodes if "httpRequest" in n.get("type", "")]
        assert len(http_nodes) >= 2  # At least 2 agents
        
        # Each node should call a specific agent endpoint
        for node in http_nodes:
            assert "/agents/" in node["parameters"]["url"]

    def test_n8n_workflow_nodes_are_connected(self, sample_yaml_file):
        """Test that nodes are properly connected."""
        from praisonai.cli.features.n8n import N8nHandler
        handler = N8nHandler()
        result = handler.convert_yaml_to_n8n(sample_yaml_file)
        
        connections = result["connections"]
        assert len(connections) > 0

    def test_n8n_workflow_name_from_yaml(self, sample_yaml_file):
        """Test that workflow name is taken from YAML."""
        from praisonai.cli.features.n8n import N8nHandler
        handler = N8nHandler()
        result = handler.convert_yaml_to_n8n(sample_yaml_file)
        
        assert result["name"] == "Test Workflow"

    def test_generate_n8n_url(self, sample_yaml_file):
        """Test URL generation for n8n."""
        from praisonai.cli.features.n8n import N8nHandler
        handler = N8nHandler()
        workflow_json = handler.convert_yaml_to_n8n(sample_yaml_file)
        url = handler.generate_n8n_url(workflow_json, "http://localhost:5678")
        
        assert url.startswith("http://localhost:5678")
        assert "workflow" in url.lower()

    def test_node_positions_are_sequential(self, sample_yaml_file):
        """Test that node positions are laid out sequentially."""
        from praisonai.cli.features.n8n import N8nHandler
        handler = N8nHandler()
        result = handler.convert_yaml_to_n8n(sample_yaml_file)
        
        nodes = result["nodes"]
        positions = [n.get("position", [0, 0]) for n in nodes]
        
        # X positions should increase for sequential workflow
        x_positions = [p[0] for p in positions]
        assert x_positions == sorted(x_positions), "Nodes should be positioned left to right"


class TestN8nCLIIntegration:
    """Tests for CLI integration of n8n feature."""
    
    def test_n8n_flag_in_argparser(self):
        """Test that --n8n flag is recognized by argparser."""
        import argparse
        # This will be tested after we add the flag to main.py
        pass

    def test_execute_method_exists(self):
        """Test that execute method exists."""
        from praisonai.cli.features.n8n import N8nHandler
        handler = N8nHandler()
        assert hasattr(handler, 'execute')
        assert callable(handler.execute)


class TestN8nWorkflowPatterns:
    """Tests for different workflow patterns."""
    
    @pytest.fixture
    def parallel_workflow_yaml(self):
        """YAML with parallel steps."""
        return """
name: Parallel Workflow

agents:
  agent1:
    name: Agent1
    role: Role1
    goal: Goal1
  agent2:
    name: Agent2
    role: Role2
    goal: Goal2

steps:
  - parallel:
      - agent: agent1
        action: "Do task 1"
      - agent: agent2
        action: "Do task 2"
"""

    @pytest.fixture
    def route_workflow_yaml(self):
        """YAML with route/decision steps."""
        return """
name: Route Workflow

agents:
  classifier:
    name: Classifier
    role: Classifier
    goal: Classify input
  handler_a:
    name: HandlerA
    role: Handler
    goal: Handle type A
  handler_b:
    name: HandlerB
    role: Handler
    goal: Handle type B

steps:
  - agent: classifier
    action: "Classify the input"
  
  - route:
      type_a: [handler_a]
      type_b: [handler_b]
"""

    def test_parallel_workflow_creates_split_node(self, parallel_workflow_yaml):
        """Test that parallel steps create appropriate n8n structure."""
        import tempfile
        import os
        from praisonai.cli.features.n8n import N8nHandler
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(parallel_workflow_yaml)
            f.flush()
            
            handler = N8nHandler()
            result = handler.convert_yaml_to_n8n(f.name)
            
            # Should have nodes for parallel execution
            assert len(result["nodes"]) >= 2
            
        os.unlink(f.name)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
