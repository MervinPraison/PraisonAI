"""
Tests for Workflow hierarchical process mode.

TDD: These tests define the expected behavior for process="hierarchical" in Workflow.
The hierarchical mode uses a manager agent to validate each step before proceeding.
"""
from unittest.mock import Mock, patch


class TestWorkflowHierarchicalFields:
    """Test that Workflow dataclass has process and manager_llm fields."""
    
    def test_workflow_has_process_field_with_default(self):
        """Workflow should have process field defaulting to 'sequential'."""
        from praisonaiagents import Workflow
        
        workflow = Workflow(steps=[])
        assert hasattr(workflow, 'process')
        assert workflow.process == "sequential"
    
    def test_workflow_accepts_process_hierarchical(self):
        """Workflow should accept process='hierarchical'."""
        from praisonaiagents import Workflow
        
        workflow = Workflow(steps=[], process="hierarchical")
        assert workflow.process == "hierarchical"
    
    def test_workflow_has_manager_llm_field(self):
        """Workflow should have manager_llm field defaulting to None."""
        from praisonaiagents import Workflow
        
        workflow = Workflow(steps=[])
        assert hasattr(workflow, 'manager_llm')
        assert workflow.manager_llm is None
    
    def test_workflow_accepts_manager_llm(self):
        """Workflow should accept manager_llm parameter."""
        from praisonaiagents import Workflow
        
        workflow = Workflow(steps=[], manager_llm="gpt-4o-mini")
        assert workflow.manager_llm == "gpt-4o-mini"


class TestWorkflowHierarchicalExecution:
    """Test hierarchical execution behavior."""
    
    def test_hierarchical_creates_manager_agent(self):
        """When process='hierarchical', run() should create a manager agent."""
        from praisonaiagents import Workflow, Agent
        
        # Create a simple workflow with hierarchical process
        mock_agent = Mock(spec=Agent)
        mock_agent.name = "test_agent"
        mock_agent.start = Mock(return_value="test output")
        
        workflow = Workflow(
            steps=[mock_agent],
            process="hierarchical",
            manager_llm="gpt-4o-mini"
        )
        
        # Mock the manager agent creation and LLM calls
        with patch.object(workflow, '_run_hierarchical') as mock_hierarchical:
            mock_hierarchical.return_value = {
                "output": "test output",
                "steps": [],
                "variables": {},
                "status": "completed"
            }
            result = workflow.run("test input")
            mock_hierarchical.assert_called_once()
    
    def test_sequential_does_not_call_hierarchical(self):
        """When process='sequential' (default), should not call _run_hierarchical."""
        from praisonaiagents import Workflow
        
        workflow = Workflow(
            steps=[],
            process="sequential"  # default
        )
        
        # Verify _run_hierarchical is not called for sequential
        with patch.object(workflow, '_run_hierarchical') as mock_hierarchical:
            mock_hierarchical.return_value = {"output": "", "steps": [], "variables": {}, "status": "completed"}
            # Run with empty steps - should complete without calling hierarchical
            workflow.run("test input")
            mock_hierarchical.assert_not_called()


class TestWorkflowHierarchicalFailure:
    """Test failure handling in hierarchical mode."""
    
    def test_manager_rejection_sets_status_failed(self):
        """When manager rejects a step, workflow status should be 'failed'."""
        from praisonaiagents import Workflow, Agent
        
        mock_agent = Mock(spec=Agent)
        mock_agent.name = "test_agent"
        
        workflow = Workflow(
            steps=[mock_agent],
            process="hierarchical",
            manager_llm="gpt-4o-mini"
        )
        
        # Simulate manager rejection
        with patch.object(workflow, '_run_hierarchical') as mock_hierarchical:
            mock_hierarchical.return_value = {
                "output": "",
                "steps": [],
                "variables": {},
                "status": "failed",
                "failure_reason": "Manager rejected: Output does not address the task"
            }
            result = workflow.run("test input")
            
            assert result["status"] == "failed"
            assert "failure_reason" in result
            assert "Manager rejected" in result["failure_reason"]
    
    def test_failure_reason_in_result(self):
        """Result dict should include failure_reason when manager rejects."""
        from praisonaiagents import Workflow, Agent
        
        mock_agent = Mock(spec=Agent)
        mock_agent.name = "test_agent"
        
        workflow = Workflow(
            steps=[mock_agent],
            process="hierarchical"
        )
        
        with patch.object(workflow, '_run_hierarchical') as mock_hierarchical:
            mock_hierarchical.return_value = {
                "output": "",
                "steps": [],
                "variables": {},
                "status": "failed",
                "failure_reason": "Step 'test_agent' failed validation"
            }
            result = workflow.run("test input")
            
            assert "failure_reason" in result
            assert result["failure_reason"] == "Step 'test_agent' failed validation"


class TestWorkflowHierarchicalYAML:
    """Test YAML parsing for hierarchical process."""
    
    def test_yaml_parser_sets_process_field(self):
        """YAML parser should set process field on Workflow."""
        from praisonaiagents.workflows.yaml_parser import YAMLWorkflowParser
        
        yaml_content = """
name: test-workflow
process: hierarchical
manager_llm: gpt-4o-mini

agents:
  researcher:
    role: Researcher
    goal: Research topics
    backstory: Expert researcher

steps:
  - agent: researcher
    action: Research the topic
"""
        parser = YAMLWorkflowParser()
        workflow = parser.parse_string(yaml_content)
        
        assert workflow.process == "hierarchical"
        assert workflow.manager_llm == "gpt-4o-mini"
    
    def test_yaml_parser_defaults_to_sequential(self):
        """YAML parser should default process to 'sequential'."""
        from praisonaiagents.workflows.yaml_parser import YAMLWorkflowParser
        
        yaml_content = """
name: test-workflow

agents:
  researcher:
    role: Researcher
    goal: Research topics
    backstory: Expert researcher

steps:
  - agent: researcher
    action: Research the topic
"""
        parser = YAMLWorkflowParser()
        workflow = parser.parse_string(yaml_content)
        
        assert workflow.process == "sequential"
        assert workflow.manager_llm is None


class TestWorkflowToDict:
    """Test that to_dict includes process and manager_llm."""
    
    def test_to_dict_includes_process(self):
        """to_dict should include process field."""
        from praisonaiagents import Workflow
        
        workflow = Workflow(steps=[], process="hierarchical")
        result = workflow.to_dict()
        
        assert "process" in result
        assert result["process"] == "hierarchical"
    
    def test_to_dict_includes_manager_llm(self):
        """to_dict should include manager_llm field."""
        from praisonaiagents import Workflow
        
        workflow = Workflow(steps=[], manager_llm="gpt-4o-mini")
        result = workflow.to_dict()
        
        assert "manager_llm" in result
        assert result["manager_llm"] == "gpt-4o-mini"
