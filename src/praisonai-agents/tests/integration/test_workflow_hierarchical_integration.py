"""
Integration tests for Workflow hierarchical process mode.

These tests validate real multi-agent workflows with hierarchical validation.
They use mocked LLM responses to avoid actual API calls while testing the full flow.
"""
from unittest.mock import patch


class TestWorkflowHierarchicalIntegration:
    """Integration tests for hierarchical workflow execution."""

    def test_research_writing_pipeline_hierarchical(self):
        """Test a research -> writing pipeline with hierarchical validation."""
        from praisonaiagents import Workflow, Agent
        
        researcher = Agent(
            name="researcher",
            role="Research Analyst",
            goal="Research topics thoroughly",
            backstory="Expert researcher with attention to detail",
            llm="gpt-4o-mini"
        )
        
        writer = Agent(
            name="writer", 
            role="Content Writer",
            goal="Write engaging content based on research",
            backstory="Professional writer who creates clear content",
            llm="gpt-4o-mini"
        )
        
        workflow = Workflow(
            name="research-writing-pipeline",
            steps=[researcher, writer],
            process="hierarchical",
            manager_llm="gpt-4o-mini"
        )
        
        assert workflow.process == "hierarchical"
        assert workflow.manager_llm == "gpt-4o-mini"
        assert len(workflow.steps) == 2
        
        with patch.object(workflow, '_run_hierarchical') as mock_hierarchical:
            mock_hierarchical.return_value = {
                "output": "Final article about AI trends",
                "steps": [
                    {"step": "researcher", "output": "Research findings...", "status": "completed"},
                    {"step": "writer", "output": "Final article about AI trends", "status": "completed"}
                ],
                "variables": {"input": "Write about AI trends"},
                "status": "completed"
            }
            
            result = workflow.run("Write about AI trends")
            
            assert result["status"] == "completed"
            assert len(result["steps"]) == 2
            assert result["steps"][0]["status"] == "completed"
            assert result["steps"][1]["status"] == "completed"
            mock_hierarchical.assert_called_once()

    def test_data_analysis_pipeline_hierarchical_failure(self):
        """Test a data analysis pipeline where manager rejects a step."""
        from praisonaiagents import Workflow, Agent
        
        collector = Agent(
            name="data_collector",
            role="Data Collector",
            goal="Collect and prepare data",
            backstory="Expert at gathering data from various sources",
            llm="gpt-4o-mini"
        )
        
        analyst = Agent(
            name="analyst",
            role="Data Analyst", 
            goal="Analyze data and find insights",
            backstory="Statistical expert who finds patterns",
            llm="gpt-4o-mini"
        )
        
        reporter = Agent(
            name="reporter",
            role="Report Writer",
            goal="Create clear reports from analysis",
            backstory="Technical writer who explains complex data",
            llm="gpt-4o-mini"
        )
        
        workflow = Workflow(
            name="data-analysis-pipeline",
            steps=[collector, analyst, reporter],
            process="hierarchical",
            manager_llm="gpt-4o-mini"
        )
        
        with patch.object(workflow, '_run_hierarchical') as mock_hierarchical:
            mock_hierarchical.return_value = {
                "output": "",
                "steps": [
                    {"step": "data_collector", "output": "Data collected", "status": "completed"},
                    {"step": "analyst", "output": "Error: insufficient data", "status": "failed", 
                     "failure_reason": "Manager rejected: Analysis output indicates error"}
                ],
                "variables": {"input": "Analyze sales data"},
                "status": "failed",
                "failure_reason": "Manager rejected step 'analyst': Analysis output indicates error"
            }
            
            result = workflow.run("Analyze sales data")
            
            assert result["status"] == "failed"
            assert "failure_reason" in result
            assert "analyst" in result["failure_reason"]
            assert len(result["steps"]) == 2
            assert result["steps"][0]["status"] == "completed"
            assert result["steps"][1]["status"] == "failed"

    def test_code_review_pipeline_hierarchical(self):
        """Test a code review pipeline with hierarchical validation."""
        from praisonaiagents import Workflow, Agent
        
        code_reader = Agent(
            name="code_reader",
            role="Code Reader",
            goal="Read and understand code structure",
            backstory="Expert at parsing and understanding codebases",
            llm="gpt-4o-mini"
        )
        
        reviewer = Agent(
            name="reviewer",
            role="Code Reviewer",
            goal="Review code for issues and improvements",
            backstory="Senior developer with code review expertise",
            llm="gpt-4o-mini"
        )
        
        suggester = Agent(
            name="suggester",
            role="Improvement Suggester",
            goal="Suggest specific code improvements",
            backstory="Expert at refactoring and optimization",
            llm="gpt-4o-mini"
        )
        
        workflow = Workflow(
            name="code-review-pipeline",
            steps=[code_reader, reviewer, suggester],
            process="hierarchical",
            manager_llm="gpt-4o-mini",
            output="verbose"
        )
        
        assert workflow.process == "hierarchical"
        assert workflow._verbose
        
        with patch.object(workflow, '_run_hierarchical') as mock_hierarchical:
            mock_hierarchical.return_value = {
                "output": "Suggested improvements: 1. Add type hints, 2. Extract method",
                "steps": [
                    {"step": "code_reader", "output": "Code structure analyzed", "status": "completed"},
                    {"step": "reviewer", "output": "Found 3 issues", "status": "completed"},
                    {"step": "suggester", "output": "Suggested improvements: 1. Add type hints, 2. Extract method", "status": "completed"}
                ],
                "variables": {},
                "status": "completed"
            }
            
            result = workflow.run("Review this Python code")
            
            assert result["status"] == "completed"
            assert len(result["steps"]) == 3
            for step in result["steps"]:
                assert step["status"] == "completed"


class TestWorkflowSequentialVsHierarchical:
    """Compare sequential and hierarchical workflow behavior."""

    def test_sequential_workflow_no_validation(self):
        """Sequential workflow should not use manager validation."""
        from praisonaiagents import Workflow, Agent
        
        agent1 = Agent(name="agent1", role="First", goal="Do first task", llm="gpt-4o-mini")
        agent2 = Agent(name="agent2", role="Second", goal="Do second task", llm="gpt-4o-mini")
        
        workflow = Workflow(
            steps=[agent1, agent2],
            process="sequential"
        )
        
        assert workflow.process == "sequential"
        
        with patch.object(workflow, '_run_hierarchical') as mock_hierarchical:
            workflow.run("")
            mock_hierarchical.assert_not_called()

    def test_hierarchical_workflow_uses_validation(self):
        """Hierarchical workflow should use manager validation."""
        from praisonaiagents import Workflow, Agent
        
        agent1 = Agent(name="agent1", role="First", goal="Do first task", llm="gpt-4o-mini")
        agent2 = Agent(name="agent2", role="Second", goal="Do second task", llm="gpt-4o-mini")
        
        workflow = Workflow(
            steps=[agent1, agent2],
            process="hierarchical",
            manager_llm="gpt-4o-mini"
        )
        
        assert workflow.process == "hierarchical"
        
        with patch.object(workflow, '_run_hierarchical') as mock_hierarchical:
            mock_hierarchical.return_value = {
                "output": "done",
                "steps": [],
                "variables": {},
                "status": "completed"
            }
            workflow.run("test")
            mock_hierarchical.assert_called_once()


class TestWorkflowHierarchicalYAMLIntegration:
    """Test hierarchical workflows parsed from YAML."""

    def test_yaml_hierarchical_workflow_parsing(self):
        """Test that YAML-defined hierarchical workflows work correctly."""
        from praisonaiagents.workflows.yaml_parser import YAMLWorkflowParser
        
        yaml_content = """
name: content-pipeline
process: hierarchical
manager_llm: gpt-4o-mini

agents:
  researcher:
    role: Research Specialist
    goal: Find accurate information
    backstory: Expert researcher
    llm: gpt-4o-mini
  
  writer:
    role: Content Writer
    goal: Write clear content
    backstory: Professional writer
    llm: gpt-4o-mini
  
  editor:
    role: Editor
    goal: Polish and improve content
    backstory: Experienced editor
    llm: gpt-4o-mini

steps:
  - agent: researcher
    action: Research the topic thoroughly
    expected_output: Comprehensive research notes
  
  - agent: writer
    action: Write article based on research
    expected_output: Draft article
  
  - agent: editor
    action: Edit and polish the article
    expected_output: Final polished article
"""
        
        parser = YAMLWorkflowParser()
        workflow = parser.parse_string(yaml_content)
        
        assert workflow.name == "content-pipeline"
        assert workflow.process == "hierarchical"
        assert workflow.manager_llm == "gpt-4o-mini"
        assert len(workflow.steps) == 3
        
        with patch.object(workflow, '_run_hierarchical') as mock_hierarchical:
            mock_hierarchical.return_value = {
                "output": "Final polished article",
                "steps": [
                    {"step": "researcher", "output": "Research notes", "status": "completed"},
                    {"step": "writer", "output": "Draft article", "status": "completed"},
                    {"step": "editor", "output": "Final polished article", "status": "completed"}
                ],
                "variables": {},
                "status": "completed"
            }
            
            result = workflow.run("Write about machine learning")
            
            assert result["status"] == "completed"
            mock_hierarchical.assert_called_once()

    def test_yaml_sequential_workflow_default(self):
        """Test that YAML workflows default to sequential process."""
        from praisonaiagents.workflows.yaml_parser import YAMLWorkflowParser
        
        yaml_content = """
name: simple-workflow

agents:
  worker:
    role: Worker
    goal: Do work
    backstory: Hard worker
    llm: gpt-4o-mini

steps:
  - agent: worker
    action: Do the task
"""
        
        parser = YAMLWorkflowParser()
        workflow = parser.parse_string(yaml_content)
        
        assert workflow.process == "sequential"
        assert workflow.manager_llm is None


class TestWorkflowHierarchicalCallbacks:
    """Test callback integration with hierarchical workflows."""

    def test_hierarchical_workflow_with_hooks_config(self):
        """Test that hierarchical workflows work with hooks configuration."""
        from praisonaiagents import Workflow, Agent
        
        agent = Agent(name="test_agent", role="Test", goal="Test", llm="gpt-4o-mini")
        
        workflow = Workflow(
            steps=[agent],
            process="hierarchical",
            manager_llm="gpt-4o-mini"
        )
        
        with patch.object(workflow, '_run_hierarchical') as mock_hierarchical:
            mock_hierarchical.return_value = {
                "output": "",
                "steps": [{"step": "test_agent", "output": "", "status": "failed"}],
                "variables": {},
                "status": "failed",
                "failure_reason": "Manager rejected step"
            }
            
            result = workflow.run("test")
            
            assert result["status"] == "failed"
            assert "failure_reason" in result


class TestWorkflowHierarchicalToDict:
    """Test serialization of hierarchical workflows."""

    def test_to_dict_includes_hierarchical_config(self):
        """Test that to_dict includes process and manager_llm."""
        from praisonaiagents import Workflow
        
        workflow = Workflow(
            name="test-workflow",
            steps=[],
            process="hierarchical",
            manager_llm="gpt-4o"
        )
        
        result = workflow.to_dict()
        
        assert result["name"] == "test-workflow"
        assert result["process"] == "hierarchical"
        assert result["manager_llm"] == "gpt-4o"

    def test_to_dict_sequential_default(self):
        """Test that to_dict shows sequential as default."""
        from praisonaiagents import Workflow
        
        workflow = Workflow(steps=[])
        
        result = workflow.to_dict()
        
        assert result["process"] == "sequential"
        assert result["manager_llm"] is None
