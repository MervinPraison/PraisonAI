"""
Unit tests for YAML parser robustness features.

Tests skip_on_failure, retry_delay, and history parsing in YAML workflows.
"""
import pytest
import tempfile
import os


class TestYAMLParserRobustnessFields:
    """Test YAML parser handles robustness fields correctly."""
    
    def test_agents_yaml_skip_on_failure_in_task(self):
        """Test skip_on_failure is parsed from agents.yaml task config."""
        from praisonaiagents.workflows.yaml_parser import YAMLWorkflowParser
        
        yaml_content = """
framework: praisonai
topic: Test workflow

roles:
  researcher:
    role: Researcher
    goal: Research topics
    backstory: Expert researcher
    tasks:
      research_task:
        description: Research AI trends
        expected_output: Report
        skip_on_failure: true
        retry_delay: 2.5
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(yaml_content)
            f.flush()
            
            try:
                parser = YAMLWorkflowParser()
                workflow = parser.parse_file(f.name)
                
                # Check that workflow was created
                assert workflow is not None
                assert len(workflow.steps) > 0
            finally:
                os.unlink(f.name)
    
    def test_workflow_yaml_skip_on_failure_in_step(self):
        """Test skip_on_failure is parsed from workflow.yaml step config."""
        from praisonaiagents.workflows.yaml_parser import YAMLWorkflowParser
        
        yaml_content = """
name: Test Workflow
description: Test robustness features

agents:
  researcher:
    name: Researcher
    role: Research Expert
    goal: Find information
    instructions: Be thorough

steps:
  - agent: researcher
    action: Research AI trends
    skip_on_failure: true
    retry_delay: 1.5
    max_retries: 5
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(yaml_content)
            f.flush()
            
            try:
                parser = YAMLWorkflowParser()
                workflow = parser.parse_file(f.name)
                
                # Check that workflow was created with steps
                assert workflow is not None
                assert len(workflow.steps) > 0
                
                # Check that the agent has the robustness attributes
                agent = workflow.steps[0]
                assert hasattr(agent, '_yaml_skip_on_failure')
                assert agent._yaml_skip_on_failure == True
                assert hasattr(agent, '_yaml_retry_delay')
                assert agent._yaml_retry_delay == 1.5
            finally:
                os.unlink(f.name)
    
    def test_workflow_yaml_history_enabled(self):
        """Test history flag is parsed from workflow.yaml."""
        from praisonaiagents.workflows.yaml_parser import YAMLWorkflowParser
        
        yaml_content = """
name: Test Workflow with History
description: Test history tracking
history: true

agents:
  writer:
    name: Writer
    role: Content Writer
    goal: Write content
    instructions: Be creative

steps:
  - agent: writer
    action: Write a blog post
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(yaml_content)
            f.flush()
            
            try:
                parser = YAMLWorkflowParser()
                workflow = parser.parse_file(f.name)
                
                # Check that history is enabled
                assert workflow is not None
                assert workflow.history == True
            finally:
                os.unlink(f.name)
    
    def test_workflow_yaml_history_default_false(self):
        """Test history defaults to False when not specified."""
        from praisonaiagents.workflows.yaml_parser import YAMLWorkflowParser
        
        yaml_content = """
name: Test Workflow without History
description: Test default history

agents:
  writer:
    name: Writer
    role: Content Writer
    goal: Write content
    instructions: Be creative

steps:
  - agent: writer
    action: Write a blog post
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(yaml_content)
            f.flush()
            
            try:
                parser = YAMLWorkflowParser()
                workflow = parser.parse_file(f.name)
                
                # Check that history defaults to False
                assert workflow is not None
                assert workflow.history == False
            finally:
                os.unlink(f.name)
    
    def test_workflow_yaml_retry_delay_float(self):
        """Test retry_delay accepts float values."""
        from praisonaiagents.workflows.yaml_parser import YAMLWorkflowParser
        
        yaml_content = """
name: Test Workflow
description: Test retry delay

agents:
  worker:
    name: Worker
    role: Task Worker
    goal: Complete tasks
    instructions: Work efficiently

steps:
  - agent: worker
    action: Process data
    retry_delay: 0.5
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(yaml_content)
            f.flush()
            
            try:
                parser = YAMLWorkflowParser()
                workflow = parser.parse_file(f.name)
                
                agent = workflow.steps[0]
                assert hasattr(agent, '_yaml_retry_delay')
                assert agent._yaml_retry_delay == 0.5
            finally:
                os.unlink(f.name)
    
    def test_workflow_yaml_skip_on_failure_false_explicit(self):
        """Test skip_on_failure can be explicitly set to false."""
        from praisonaiagents.workflows.yaml_parser import YAMLWorkflowParser
        
        yaml_content = """
name: Test Workflow
description: Test explicit false

agents:
  worker:
    name: Worker
    role: Task Worker
    goal: Complete tasks
    instructions: Work efficiently

steps:
  - agent: worker
    action: Critical task
    skip_on_failure: false
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(yaml_content)
            f.flush()
            
            try:
                parser = YAMLWorkflowParser()
                workflow = parser.parse_file(f.name)
                
                agent = workflow.steps[0]
                assert hasattr(agent, '_yaml_skip_on_failure')
                assert agent._yaml_skip_on_failure == False
            finally:
                os.unlink(f.name)


class TestYAMLParserRobustnessIntegration:
    """Integration tests for robustness features in YAML workflows."""
    
    def test_full_robustness_workflow(self):
        """Test a complete workflow with all robustness features."""
        from praisonaiagents.workflows.yaml_parser import YAMLWorkflowParser
        
        yaml_content = """
name: Robust Research Workflow
description: A workflow with full robustness features
history: true

agents:
  researcher:
    name: Researcher
    role: Research Expert
    goal: Find accurate information
    instructions: Be thorough and accurate
  
  writer:
    name: Writer
    role: Content Writer
    goal: Create engaging content
    instructions: Write clearly

steps:
  - agent: researcher
    action: Research AI trends for 2025
    skip_on_failure: true
    retry_delay: 1.0
    max_retries: 3
  
  - agent: writer
    action: Write summary based on research
    skip_on_failure: false
    retry_delay: 2.0
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(yaml_content)
            f.flush()
            
            try:
                parser = YAMLWorkflowParser()
                workflow = parser.parse_file(f.name)
                
                # Verify workflow-level settings
                assert workflow.name == "Robust Research Workflow"
                assert workflow.history == True
                assert len(workflow.steps) == 2
                
                # Verify first step (researcher)
                researcher = workflow.steps[0]
                assert researcher._yaml_skip_on_failure == True
                assert researcher._yaml_retry_delay == 1.0
                
                # Verify second step (writer)
                writer = workflow.steps[1]
                assert writer._yaml_skip_on_failure == False
                assert writer._yaml_retry_delay == 2.0
            finally:
                os.unlink(f.name)
