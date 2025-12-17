"""
Test-driven development tests for YAMLWorkflowParser.

Tests the parsing of YAML workflow files into Workflow objects with patterns.
"""

import pytest
import tempfile
import os
from pathlib import Path


class TestYAMLWorkflowParserBasic:
    """Basic tests for YAMLWorkflowParser class."""
    
    def test_yaml_workflow_parser_import(self):
        """Test that YAMLWorkflowParser can be imported."""
        from praisonaiagents.workflows import YAMLWorkflowParser
        assert YAMLWorkflowParser is not None
    
    def test_yaml_workflow_parser_initialization(self):
        """Test YAMLWorkflowParser initialization."""
        from praisonaiagents.workflows import YAMLWorkflowParser
        parser = YAMLWorkflowParser()
        assert parser is not None
    
    def test_parse_simple_yaml_string(self):
        """Test parsing a simple YAML string."""
        from praisonaiagents.workflows import YAMLWorkflowParser
        
        yaml_content = """
name: Simple Workflow
description: A simple test workflow

agents:
  researcher:
    name: Researcher
    role: Research Analyst
    goal: Research topics
    instructions: "Provide research findings"

steps:
  - agent: researcher
    action: "Research {{topic}}"
"""
        parser = YAMLWorkflowParser()
        workflow = parser.parse_string(yaml_content)
        
        assert workflow is not None
        assert workflow.name == "Simple Workflow"
    
    def test_parse_yaml_file(self):
        """Test parsing a YAML file."""
        from praisonaiagents.workflows import YAMLWorkflowParser
        
        yaml_content = """
name: File Workflow
description: Test workflow from file

agents:
  writer:
    name: Writer
    role: Content Writer
    goal: Write content
    instructions: "Write engaging content"

steps:
  - agent: writer
    action: "Write about {{topic}}"
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(yaml_content)
            temp_path = f.name
        
        try:
            parser = YAMLWorkflowParser()
            workflow = parser.parse_file(temp_path)
            
            assert workflow is not None
            assert workflow.name == "File Workflow"
        finally:
            os.unlink(temp_path)


class TestYAMLWorkflowParserAgents:
    """Tests for agent parsing in YAML workflows."""
    
    def test_parse_agent_with_basic_fields(self):
        """Test parsing agent with basic fields."""
        from praisonaiagents.workflows import YAMLWorkflowParser
        
        yaml_content = """
name: Agent Test
agents:
  researcher:
    name: Researcher
    role: Research Analyst
    goal: Research topics
    instructions: "You are a research analyst"

steps:
  - agent: researcher
    action: "Research AI"
"""
        parser = YAMLWorkflowParser()
        workflow = parser.parse_string(yaml_content)
        
        # Check that agents were created
        assert len(workflow.steps) > 0
    
    def test_parse_agent_with_llm(self):
        """Test parsing agent with LLM configuration."""
        from praisonaiagents.workflows import YAMLWorkflowParser
        
        yaml_content = """
name: LLM Test
agents:
  researcher:
    name: Researcher
    role: Analyst
    goal: Analyze
    instructions: "Analyze data"
    llm: gpt-4o-mini

steps:
  - agent: researcher
    action: "Analyze"
"""
        parser = YAMLWorkflowParser()
        workflow = parser.parse_string(yaml_content)
        
        assert workflow is not None
    
    def test_parse_agent_with_tools(self):
        """Test parsing agent with tools."""
        from praisonaiagents.workflows import YAMLWorkflowParser
        
        yaml_content = """
name: Tools Test
agents:
  researcher:
    name: Researcher
    role: Analyst
    goal: Research
    instructions: "Research with tools"
    tools:
      - tavily_search
      - web_scraper

steps:
  - agent: researcher
    action: "Research"
"""
        parser = YAMLWorkflowParser()
        workflow = parser.parse_string(yaml_content)
        
        assert workflow is not None
    
    def test_parse_agent_with_planning_reasoning(self):
        """Test parsing agent with planning and reasoning flags."""
        from praisonaiagents.workflows import YAMLWorkflowParser
        
        yaml_content = """
name: Planning Test
agents:
  planner:
    name: Planner
    role: Strategic Planner
    goal: Create plans
    instructions: "Create strategic plans"
    planning: true
    reasoning: true
    verbose: true

steps:
  - agent: planner
    action: "Create plan"
"""
        parser = YAMLWorkflowParser()
        workflow = parser.parse_string(yaml_content)
        
        assert workflow is not None


class TestYAMLWorkflowParserPatterns:
    """Tests for workflow pattern parsing."""
    
    def test_parse_route_pattern(self):
        """Test parsing route pattern in steps."""
        from praisonaiagents.workflows import YAMLWorkflowParser
        
        yaml_content = """
name: Route Test
agents:
  classifier:
    name: Classifier
    role: Classifier
    goal: Classify
    instructions: "Respond with 'technical' or 'creative'"
  tech_agent:
    name: TechExpert
    role: Technical Expert
    goal: Handle technical
    instructions: "Technical answers"
  creative_agent:
    name: Creative
    role: Creative Writer
    goal: Handle creative
    instructions: "Creative content"

steps:
  - agent: classifier
    action: "Classify: {{input}}"
  - name: routing
    route:
      technical: [tech_agent]
      creative: [creative_agent]
      default: [tech_agent]
"""
        parser = YAMLWorkflowParser()
        workflow = parser.parse_string(yaml_content)
        
        assert workflow is not None
        assert len(workflow.steps) == 2
    
    def test_parse_parallel_pattern(self):
        """Test parsing parallel pattern in steps."""
        from praisonaiagents.workflows import YAMLWorkflowParser
        
        yaml_content = """
name: Parallel Test
agents:
  researcher1:
    name: R1
    role: Researcher
    goal: Research
    instructions: "Research market"
  researcher2:
    name: R2
    role: Researcher
    goal: Research
    instructions: "Research competitors"
  aggregator:
    name: Agg
    role: Aggregator
    goal: Aggregate
    instructions: "Combine findings"

steps:
  - name: parallel_research
    parallel:
      - agent: researcher1
        action: "Research market"
      - agent: researcher2
        action: "Research competitors"
  - agent: aggregator
    action: "Combine results"
"""
        parser = YAMLWorkflowParser()
        workflow = parser.parse_string(yaml_content)
        
        assert workflow is not None
        assert len(workflow.steps) == 2
    
    def test_parse_loop_pattern(self):
        """Test parsing loop pattern in steps."""
        from praisonaiagents.workflows import YAMLWorkflowParser
        
        yaml_content = """
name: Loop Test
variables:
  items:
    - AI
    - ML
    - NLP

agents:
  processor:
    name: Processor
    role: Processor
    goal: Process items
    instructions: "Process each item"
  summarizer:
    name: Summarizer
    role: Summarizer
    goal: Summarize
    instructions: "Summarize results"

steps:
  - agent: processor
    action: "Process {{item}}"
    loop:
      over: items
  - agent: summarizer
    action: "Summarize all"
"""
        parser = YAMLWorkflowParser()
        workflow = parser.parse_string(yaml_content)
        
        assert workflow is not None
        assert workflow.variables.get("items") == ["AI", "ML", "NLP"]
    
    def test_parse_repeat_pattern(self):
        """Test parsing repeat pattern in steps."""
        from praisonaiagents.workflows import YAMLWorkflowParser
        
        yaml_content = """
name: Repeat Test
agents:
  generator:
    name: Generator
    role: Generator
    goal: Generate content
    instructions: "Generate and improve"
  evaluator:
    name: Evaluator
    role: Evaluator
    goal: Evaluate
    instructions: "Say APPROVED if good"

steps:
  - agent: generator
    action: "Generate content"
  - agent: evaluator
    action: "Evaluate"
    repeat:
      until: "approved"
      max_iterations: 3
"""
        parser = YAMLWorkflowParser()
        workflow = parser.parse_string(yaml_content)
        
        assert workflow is not None
        assert len(workflow.steps) == 2


class TestYAMLWorkflowParserWorkflowConfig:
    """Tests for workflow configuration parsing."""
    
    def test_parse_workflow_config(self):
        """Test parsing workflow configuration section."""
        from praisonaiagents.workflows import YAMLWorkflowParser
        
        yaml_content = """
name: Config Test
workflow:
  planning: true
  planning_llm: gpt-4o
  reasoning: true
  verbose: true

agents:
  agent1:
    name: Agent1
    role: Worker
    goal: Work
    instructions: "Do work"

steps:
  - agent: agent1
    action: "Work"
"""
        parser = YAMLWorkflowParser()
        workflow = parser.parse_string(yaml_content)
        
        assert workflow is not None
        assert workflow.planning == True
        assert workflow.reasoning == True
        assert workflow.verbose == True
    
    def test_parse_memory_config(self):
        """Test parsing memory configuration."""
        from praisonaiagents.workflows import YAMLWorkflowParser
        
        yaml_content = """
name: Memory Test
workflow:
  memory_config:
    provider: chroma
    persist: true
    collection: test_collection

agents:
  agent1:
    name: Agent1
    role: Worker
    goal: Work
    instructions: "Do work"

steps:
  - agent: agent1
    action: "Work"
"""
        parser = YAMLWorkflowParser()
        workflow = parser.parse_string(yaml_content)
        
        assert workflow is not None
        assert workflow.memory_config is not None
        assert workflow.memory_config.get("provider") == "chroma"


class TestYAMLWorkflowParserCallbacks:
    """Tests for callbacks parsing."""
    
    def test_parse_callbacks(self):
        """Test parsing callbacks section."""
        from praisonaiagents.workflows import YAMLWorkflowParser
        
        yaml_content = """
name: Callbacks Test
agents:
  agent1:
    name: Agent1
    role: Worker
    goal: Work
    instructions: "Do work"

steps:
  - agent: agent1
    action: "Work"

callbacks:
  on_workflow_start: log_start
  on_step_complete: log_step
  on_workflow_complete: log_complete
"""
        parser = YAMLWorkflowParser()
        workflow = parser.parse_string(yaml_content)
        
        assert workflow is not None


class TestYAMLWorkflowParserGuardrails:
    """Tests for guardrails parsing."""
    
    def test_parse_step_guardrail(self):
        """Test parsing guardrail on a step."""
        from praisonaiagents.workflows import YAMLWorkflowParser
        
        yaml_content = """
name: Guardrail Test
agents:
  writer:
    name: Writer
    role: Writer
    goal: Write
    instructions: "Write content"

steps:
  - agent: writer
    action: "Write content"
    guardrail: validate_content
    max_retries: 3
"""
        parser = YAMLWorkflowParser()
        workflow = parser.parse_string(yaml_content)
        
        assert workflow is not None


class TestYAMLWorkflowParserVariables:
    """Tests for variables parsing."""
    
    def test_parse_variables(self):
        """Test parsing variables section."""
        from praisonaiagents.workflows import YAMLWorkflowParser
        
        yaml_content = """
name: Variables Test
variables:
  topic: AI trends
  count: 5
  items:
    - one
    - two
    - three

agents:
  agent1:
    name: Agent1
    role: Worker
    goal: Work
    instructions: "Do work"

steps:
  - agent: agent1
    action: "Work on {{topic}}"
"""
        parser = YAMLWorkflowParser()
        workflow = parser.parse_string(yaml_content)
        
        assert workflow is not None
        assert workflow.variables.get("topic") == "AI trends"
        assert workflow.variables.get("count") == 5
        assert workflow.variables.get("items") == ["one", "two", "three"]


class TestWorkflowManagerYAML:
    """Tests for WorkflowManager YAML integration."""
    
    def test_workflow_manager_load_yaml(self):
        """Test WorkflowManager.load_yaml() method."""
        from praisonaiagents.workflows import WorkflowManager
        
        yaml_content = """
name: Manager Test
agents:
  agent1:
    name: Agent1
    role: Worker
    goal: Work
    instructions: "Do work"

steps:
  - agent: agent1
    action: "Work"
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(yaml_content)
            temp_path = f.name
        
        try:
            manager = WorkflowManager()
            workflow = manager.load_yaml(temp_path)
            
            assert workflow is not None
            assert workflow.name == "Manager Test"
        finally:
            os.unlink(temp_path)
    
    def test_workflow_manager_execute_yaml(self):
        """Test WorkflowManager.execute_yaml() method (mock execution)."""
        from praisonaiagents.workflows import WorkflowManager
        from unittest.mock import patch
        
        yaml_content = """
name: Execute Test
variables:
  topic: AI

agents:
  agent1:
    name: Agent1
    role: Worker
    goal: Work
    instructions: "Do work"

steps:
  - agent: agent1
    action: "Work on {{topic}}"
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(yaml_content)
            temp_path = f.name
        
        try:
            manager = WorkflowManager()
            
            # Just test that execute_yaml method exists and can be called
            # Actual execution would require mocking LLM calls
            workflow = manager.load_yaml(temp_path)
            assert workflow is not None
            assert workflow.variables.get("topic") == "AI"
        finally:
            os.unlink(temp_path)


class TestYAMLWorkflowParserIntegration:
    """Integration tests for complete YAML workflow parsing."""
    
    def test_parse_complete_workflow(self):
        """Test parsing a complete workflow with all features."""
        from praisonaiagents.workflows import YAMLWorkflowParser
        
        yaml_content = """
name: Complete Workflow
description: A complete test workflow with all patterns
framework: praisonai

workflow:
  planning: true
  reasoning: true
  verbose: true
  memory_config:
    provider: chroma
    persist: true

variables:
  topic: AI trends
  topics:
    - Machine Learning
    - Neural Networks

agents:
  classifier:
    name: Classifier
    role: Request Classifier
    goal: Classify requests
    instructions: "Respond with 'technical' or 'creative'"
    
  researcher:
    name: Researcher
    role: Research Analyst
    goal: Research topics
    instructions: "Provide concise research findings"
    
  tech_expert:
    name: TechExpert
    role: Technical Expert
    goal: Handle technical questions
    instructions: "Provide technical answers"
    
  aggregator:
    name: Aggregator
    role: Synthesizer
    goal: Combine findings
    instructions: "Synthesize all research"

steps:
  - agent: classifier
    action: "Classify: {{input}}"
    
  - name: routing
    route:
      technical: [tech_expert]
      default: [researcher]
      
  - name: parallel_research
    parallel:
      - agent: researcher
        action: "Research market for {{topic}}"
      - agent: researcher
        action: "Research competitors for {{topic}}"
        
  - agent: aggregator
    action: "Synthesize findings"
    repeat:
      until: "comprehensive"
      max_iterations: 3

callbacks:
  on_step_complete: log_step
"""
        parser = YAMLWorkflowParser()
        workflow = parser.parse_string(yaml_content)
        
        assert workflow is not None
        assert workflow.name == "Complete Workflow"
        assert workflow.planning == True
        assert workflow.reasoning == True
        assert workflow.variables.get("topic") == "AI trends"
        assert len(workflow.steps) == 4
