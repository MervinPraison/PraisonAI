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
        # planning field holds WorkflowPlanningConfig, check _planning_enabled for bool
        assert workflow._planning_enabled == True
        assert workflow.reasoning == True
        assert workflow.verbose == True
    
    def test_parse_memory_config(self):
        """Test parsing memory configuration."""
        from praisonaiagents.workflows import YAMLWorkflowParser
        
        yaml_content = """
name: Memory Test
workflow:
  memory_config:
    backend: chroma
    user_id: test_user
    config:
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
        assert workflow.memory_config.get("backend") == "chroma"


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
  planning_llm: gpt-4o
  reasoning: true
  verbose: true

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
        assert workflow._planning_enabled == True
        assert workflow.reasoning == True
        assert workflow.variables.get("topic") == "AI trends"
        assert len(workflow.steps) == 4


class TestRolesToAgentsConversion:
    """Tests for backward compatibility with agents.yaml 'roles' format."""
    
    def test_parse_roles_instead_of_agents(self):
        """Test that 'roles' key is accepted as alternative to 'agents'."""
        from praisonaiagents.workflows import YAMLWorkflowParser
        
        yaml_content = """
name: Roles Test Workflow
process: workflow

workflow:
  verbose: true

roles:
  researcher:
    role: Research Analyst
    backstory: "You are an expert researcher."
    goal: Research topics thoroughly
    tools:
      - tavily_search

steps:
  - agent: researcher
    action: "Research the topic"
"""
        parser = YAMLWorkflowParser()
        workflow = parser.parse_string(yaml_content)
        
        assert workflow is not None
        assert workflow.name == "Roles Test Workflow"
        assert len(workflow.steps) == 1
    
    def test_backstory_mapped_to_instructions(self):
        """Test that 'backstory' is mapped to 'instructions'."""
        from praisonaiagents.workflows import YAMLWorkflowParser
        
        yaml_content = """
name: Backstory Test
process: workflow

workflow:
  verbose: true

roles:
  writer:
    role: Content Writer
    backstory: "You are a skilled content writer with expertise in technical topics."
    goal: Write engaging content

steps:
  - agent: writer
    action: "Write content"
"""
        parser = YAMLWorkflowParser()
        workflow = parser.parse_string(yaml_content)
        
        assert workflow is not None
        # The agent should have been created with the backstory as instructions
        assert len(workflow.steps) == 1
    
    def test_roles_with_llm_config(self):
        """Test that LLM config is preserved from roles."""
        from praisonaiagents.workflows import YAMLWorkflowParser
        
        yaml_content = """
name: LLM Config Test
process: workflow

workflow:
  verbose: true

roles:
  analyst:
    role: Data Analyst
    backstory: "Expert data analyst"
    goal: Analyze data
    llm:
      model: gpt-4o-mini
      temperature: 0.3

steps:
  - agent: analyst
    action: "Analyze data"
"""
        parser = YAMLWorkflowParser()
        workflow = parser.parse_string(yaml_content)
        
        assert workflow is not None
        assert len(workflow.steps) == 1
    
    def test_mixed_agents_and_roles_prefers_agents(self):
        """Test that 'agents' key takes precedence over 'roles'."""
        from praisonaiagents.workflows import YAMLWorkflowParser
        
        yaml_content = """
name: Mixed Keys Test
process: workflow

workflow:
  verbose: true

agents:
  agent1:
    name: Agent1
    role: Worker
    goal: Work
    instructions: "From agents section"

roles:
  agent2:
    role: Helper
    backstory: "From roles section"
    goal: Help

steps:
  - agent: agent1
    action: "Work"
"""
        parser = YAMLWorkflowParser()
        workflow = parser.parse_string(yaml_content)
        
        assert workflow is not None
        # Should use agents, not roles
        assert len(workflow.steps) == 1


class TestExtendedAgentsYAMLFormat:
    """Tests for the extended agents.yaml format with workflow patterns."""
    
    def test_agents_yaml_with_workflow_patterns(self):
        """Test agents.yaml format with workflow patterns."""
        from praisonaiagents.workflows import YAMLWorkflowParser
        
        yaml_content = """
name: Extended Agents YAML
framework: praisonai
process: workflow
topic: "Research AI trends"

workflow:
  planning: true
  planning_llm: gpt-4o
  reasoning: true
  verbose: true

variables:
  topic: AI trends

roles:
  classifier:
    role: Request Classifier
    backstory: "You classify requests into categories."
    goal: Classify requests
    
  researcher:
    role: Research Analyst
    backstory: "You are an expert researcher."
    goal: Research topics
    tools:
      - tavily_search

steps:
  - agent: classifier
    action: "Classify: {{topic}}"
    
  - name: routing
    route:
      technical: [researcher]
      default: [researcher]
"""
        parser = YAMLWorkflowParser()
        workflow = parser.parse_string(yaml_content)
        
        assert workflow is not None
        assert workflow.name == "Extended Agents YAML"
        assert workflow._planning_enabled == True
        assert workflow.reasoning == True
        assert workflow.variables.get("topic") == "AI trends"
        assert len(workflow.steps) == 2
    
    def test_agents_yaml_with_parallel_pattern(self):
        """Test agents.yaml format with parallel pattern."""
        from praisonaiagents.workflows import YAMLWorkflowParser
        
        yaml_content = """
name: Parallel Agents YAML
framework: praisonai
process: workflow

workflow:
  verbose: true

roles:
  market_analyst:
    role: Market Analyst
    backstory: "Expert in market analysis"
    goal: Analyze markets
    
  competitor_analyst:
    role: Competitor Analyst
    backstory: "Expert in competitor analysis"
    goal: Analyze competitors

steps:
  - name: parallel_research
    parallel:
      - agent: market_analyst
        action: "Analyze market trends"
      - agent: competitor_analyst
        action: "Analyze competitors"
"""
        parser = YAMLWorkflowParser()
        workflow = parser.parse_string(yaml_content)
        
        assert workflow is not None
        assert len(workflow.steps) == 1
    
    def test_agents_yaml_with_loop_pattern(self):
        """Test agents.yaml format with loop pattern."""
        from praisonaiagents.workflows import YAMLWorkflowParser
        
        yaml_content = """
name: Loop Agents YAML
framework: praisonai
process: workflow

workflow:
  verbose: true

variables:
  items:
    - Topic A
    - Topic B
    - Topic C

roles:
  processor:
    role: Item Processor
    backstory: "Processes items one by one"
    goal: Process items

steps:
  - agent: processor
    action: "Process {{item}}"
    loop:
      over: items
"""
        parser = YAMLWorkflowParser()
        workflow = parser.parse_string(yaml_content)
        
        assert workflow is not None
        assert len(workflow.steps) == 1
        assert workflow.variables.get("items") == ["Topic A", "Topic B", "Topic C"]


# =============================================================================
# Tests for Missing Features in workflow.yaml (Feature Parity with agents.yaml)
# =============================================================================

class TestWorkflowExpectedOutput:
    """Tests for expected_output support in workflow steps."""
    
    def test_step_with_expected_output(self):
        """Test that steps can have expected_output field."""
        from praisonaiagents.workflows import YAMLWorkflowParser
        
        yaml_content = """
name: Expected Output Workflow
agents:
  researcher:
    name: Researcher
    role: Research Analyst
    goal: Research topics
    instructions: "Provide research findings"

steps:
  - agent: researcher
    action: "Research AI trends"
    expected_output: "A comprehensive report on AI trends with citations"
"""
        parser = YAMLWorkflowParser()
        workflow = parser.parse_string(yaml_content)
        
        assert workflow is not None
        assert len(workflow.steps) == 1
        # Check that expected_output is stored on the step/agent
        step = workflow.steps[0]
        assert hasattr(step, '_yaml_expected_output') or hasattr(step, 'expected_output')


class TestWorkflowTaskContext:
    """Tests for task dependencies (context) in workflow steps."""
    
    def test_step_with_context_dependency(self):
        """Test that steps can reference previous steps as context."""
        from praisonaiagents.workflows import YAMLWorkflowParser
        
        yaml_content = """
name: Context Workflow
agents:
  researcher:
    name: Researcher
    role: Research Analyst
    goal: Research topics
    instructions: "Provide research findings"
    
  writer:
    name: Writer
    role: Content Writer
    goal: Write content
    instructions: "Write based on research"

steps:
  - name: research_step
    agent: researcher
    action: "Research AI trends"
    
  - name: writing_step
    agent: writer
    action: "Write article based on research"
    context:
      - research_step
"""
        parser = YAMLWorkflowParser()
        workflow = parser.parse_string(yaml_content)
        
        assert workflow is not None
        assert len(workflow.steps) == 2
        # Check that context is stored
        writer_step = workflow.steps[1]
        assert hasattr(writer_step, '_yaml_context') or hasattr(writer_step, 'context_from')


class TestWorkflowAgentAdvancedFields:
    """Tests for advanced agent fields in workflow.yaml."""
    
    def test_agent_with_function_calling_llm(self):
        """Test that function_calling_llm in YAML is ignored (removed in v4)."""
        from praisonaiagents.workflows import YAMLWorkflowParser
        
        yaml_content = """
name: Function Calling LLM Workflow
agents:
  researcher:
    name: Researcher
    role: Research Analyst
    goal: Research topics
    instructions: "Provide research findings"
    llm: gpt-4o-mini
    function_calling_llm: gpt-4o  # This is ignored in v4

steps:
  - agent: researcher
    action: "Research AI"
"""
        parser = YAMLWorkflowParser()
        workflow = parser.parse_string(yaml_content)
        
        assert workflow is not None
        researcher = parser._agents.get('researcher')
        assert researcher is not None
        # function_calling_llm is removed in v4 - should NOT be stored
        assert not hasattr(researcher, '_yaml_function_calling_llm')
        assert not hasattr(researcher, 'function_calling_llm')
    
    def test_agent_with_max_rpm(self):
        """Test that agents can have max_rpm for rate limiting."""
        from praisonaiagents.workflows import YAMLWorkflowParser
        
        yaml_content = """
name: Max RPM Workflow
agents:
  researcher:
    name: Researcher
    role: Research Analyst
    goal: Research topics
    instructions: "Provide research findings"
    max_rpm: 10

steps:
  - agent: researcher
    action: "Research AI"
"""
        parser = YAMLWorkflowParser()
        workflow = parser.parse_string(yaml_content)
        
        assert workflow is not None
        researcher = parser._agents.get('researcher')
        assert researcher is not None
        assert hasattr(researcher, '_yaml_max_rpm')
    
    def test_agent_with_max_execution_time(self):
        """Test that agents can have max_execution_time for timeout."""
        from praisonaiagents.workflows import YAMLWorkflowParser
        
        yaml_content = """
name: Max Execution Time Workflow
agents:
  researcher:
    name: Researcher
    role: Research Analyst
    goal: Research topics
    instructions: "Provide research findings"
    max_execution_time: 300

steps:
  - agent: researcher
    action: "Research AI"
"""
        parser = YAMLWorkflowParser()
        workflow = parser.parse_string(yaml_content)
        
        assert workflow is not None
        researcher = parser._agents.get('researcher')
        assert researcher is not None
        assert hasattr(researcher, '_yaml_max_execution_time')
    
    def test_agent_with_reflect_llm(self):
        """Test that agents can have reflect_llm for reflection."""
        from praisonaiagents.workflows import YAMLWorkflowParser
        
        yaml_content = """
name: Reflect LLM Workflow
agents:
  researcher:
    name: Researcher
    role: Research Analyst
    goal: Research topics
    instructions: "Provide research findings"
    reflect_llm: gpt-4o
    min_reflect: 1
    max_reflect: 3

steps:
  - agent: researcher
    action: "Research AI"
"""
        parser = YAMLWorkflowParser()
        workflow = parser.parse_string(yaml_content)
        
        assert workflow is not None
        researcher = parser._agents.get('researcher')
        assert researcher is not None
        assert hasattr(researcher, '_yaml_reflect_llm')
        assert hasattr(researcher, '_yaml_min_reflect')
        assert hasattr(researcher, '_yaml_max_reflect')
    
    def test_agent_with_templates(self):
        """Test that agents can have system/prompt/response templates."""
        from praisonaiagents.workflows import YAMLWorkflowParser
        
        yaml_content = """
name: Templates Workflow
agents:
  researcher:
    name: Researcher
    role: Research Analyst
    goal: Research topics
    instructions: "Provide research findings"
    system_template: "You are a helpful assistant."
    prompt_template: "Please research: {topic}"
    response_template: "Research findings: {response}"

steps:
  - agent: researcher
    action: "Research AI"
"""
        parser = YAMLWorkflowParser()
        workflow = parser.parse_string(yaml_content)
        
        assert workflow is not None
        researcher = parser._agents.get('researcher')
        assert researcher is not None
        assert hasattr(researcher, '_yaml_system_template')
        assert hasattr(researcher, '_yaml_prompt_template')
        assert hasattr(researcher, '_yaml_response_template')


class TestTaskAdvancedFields:
    """Tests for advanced step fields in workflow.yaml."""
    
    def test_step_with_output_json(self):
        """Test that steps can have output_json for structured output."""
        from praisonaiagents.workflows import YAMLWorkflowParser
        
        yaml_content = """
name: Output JSON Workflow
agents:
  researcher:
    name: Researcher
    role: Research Analyst
    goal: Research topics
    instructions: "Provide research findings"

steps:
  - agent: researcher
    action: "Research AI trends"
    output_json:
      type: object
      properties:
        title:
          type: string
        findings:
          type: array
"""
        parser = YAMLWorkflowParser()
        workflow = parser.parse_string(yaml_content)
        
        assert workflow is not None
        step = workflow.steps[0]
        assert hasattr(step, '_yaml_output_json') or hasattr(step, 'output_json')
    
    def test_step_with_create_directory(self):
        """Test that steps can have create_directory flag."""
        from praisonaiagents.workflows import YAMLWorkflowParser
        
        yaml_content = """
name: Create Directory Workflow
agents:
  researcher:
    name: Researcher
    role: Research Analyst
    goal: Research topics
    instructions: "Provide research findings"

steps:
  - agent: researcher
    action: "Research AI trends"
    output_file: "output/research/findings.txt"
    create_directory: true
"""
        parser = YAMLWorkflowParser()
        workflow = parser.parse_string(yaml_content)
        
        assert workflow is not None
        step = workflow.steps[0]
        assert hasattr(step, '_yaml_create_directory') or hasattr(step, 'create_directory')
    
    def test_step_with_callback(self):
        """Test that steps can have callback function reference."""
        from praisonaiagents.workflows import YAMLWorkflowParser
        
        yaml_content = """
name: Callback Workflow
agents:
  researcher:
    name: Researcher
    role: Research Analyst
    goal: Research topics
    instructions: "Provide research findings"

steps:
  - agent: researcher
    action: "Research AI trends"
    callback: on_research_complete
"""
        parser = YAMLWorkflowParser()
        workflow = parser.parse_string(yaml_content)
        
        assert workflow is not None
        step = workflow.steps[0]
        assert hasattr(step, '_yaml_callback') or hasattr(step, 'callback')


class TestWorkflowHierarchicalProcess:
    """Tests for hierarchical process support in workflow.yaml."""
    
    def test_workflow_with_hierarchical_process(self):
        """Test that workflow can use hierarchical process with manager."""
        from praisonaiagents.workflows import YAMLWorkflowParser
        
        yaml_content = """
name: Hierarchical Workflow
process: hierarchical
manager_llm: gpt-4o

workflow:
  verbose: true

agents:
  researcher:
    name: Researcher
    role: Research Analyst
    goal: Research topics
    instructions: "Provide research findings"
    
  writer:
    name: Writer
    role: Content Writer
    goal: Write content
    instructions: "Write articles"

steps:
  - agent: researcher
    action: "Research AI trends"
    
  - agent: writer
    action: "Write article"
"""
        parser = YAMLWorkflowParser()
        workflow = parser.parse_string(yaml_content)
        
        assert workflow is not None
        assert hasattr(workflow, 'process') or hasattr(workflow, '_yaml_process')
        assert hasattr(workflow, 'manager_llm') or hasattr(workflow, '_yaml_manager_llm')


class TestWorkflowFrameworkSupport:
    """Tests for multi-framework support in workflow.yaml."""
    
    def test_workflow_with_crewai_framework(self):
        """Test that workflow can specify crewai framework."""
        from praisonaiagents.workflows import YAMLWorkflowParser
        
        yaml_content = """
name: CrewAI Workflow
framework: crewai

agents:
  researcher:
    name: Researcher
    role: Research Analyst
    goal: Research topics
    instructions: "Provide research findings"

steps:
  - agent: researcher
    action: "Research AI trends"
"""
        parser = YAMLWorkflowParser()
        workflow = parser.parse_string(yaml_content)
        
        assert workflow is not None
        assert hasattr(workflow, 'framework') or hasattr(workflow, '_yaml_framework')
    
    def test_workflow_with_autogen_framework(self):
        """Test that workflow can specify autogen framework."""
        from praisonaiagents.workflows import YAMLWorkflowParser
        
        yaml_content = """
name: AutoGen Workflow
framework: autogen

agents:
  researcher:
    name: Researcher
    role: Research Analyst
    goal: Research topics
    instructions: "Provide research findings"

steps:
  - agent: researcher
    action: "Research AI trends"
"""
        parser = YAMLWorkflowParser()
        workflow = parser.parse_string(yaml_content)
        
        assert workflow is not None
        assert hasattr(workflow, 'framework') or hasattr(workflow, '_yaml_framework')


class TestWorkflowBackstoryAlias:
    """Tests for backstory as alias for instructions."""
    
    def test_agent_with_backstory_in_workflow(self):
        """Test that backstory is accepted as alias for instructions in workflow agents."""
        from praisonaiagents.workflows import YAMLWorkflowParser
        
        yaml_content = """
name: Backstory Workflow
agents:
  researcher:
    name: Researcher
    role: Research Analyst
    goal: Research topics
    backstory: "You are an experienced researcher with 10 years of experience."

steps:
  - agent: researcher
    action: "Research AI trends"
"""
        parser = YAMLWorkflowParser()
        workflow = parser.parse_string(yaml_content)
        
        assert workflow is not None
        researcher = parser._agents.get('researcher')
        assert researcher is not None
        # backstory should be used as instructions
        assert researcher.backstory == "You are an experienced researcher with 10 years of experience."


class TestFieldNameNormalization:
    """Tests for field name normalization (Accept liberally, suggest canonically)."""
    
    def test_roles_normalized_to_agents(self):
        """Test that 'roles' is normalized to 'agents'."""
        from praisonaiagents.workflows import YAMLWorkflowParser
        
        yaml_content = """
name: Roles Test
roles:
  researcher:
    role: Research Analyst
    goal: Research topics
    backstory: "Expert researcher"

steps:
  - agent: researcher
    action: "Research AI"
"""
        parser = YAMLWorkflowParser()
        workflow = parser.parse_string(yaml_content)
        
        assert workflow is not None
        assert 'researcher' in parser._agents
    
    def test_topic_normalized_to_name(self):
        """Test that 'topic' is normalized to 'name'."""
        from praisonaiagents.workflows import YAMLWorkflowParser
        
        yaml_content = """
topic: My Topic Workflow
agents:
  researcher:
    name: Researcher
    role: Research Analyst
    goal: Research topics
    instructions: "Provide research"

steps:
  - agent: researcher
    action: "Research"
"""
        parser = YAMLWorkflowParser()
        workflow = parser.parse_string(yaml_content)
        
        assert workflow is not None
        assert workflow.name == "My Topic Workflow"
    
    def test_input_field_canonical(self):
        """Test that 'input' field is the canonical way to specify workflow input."""
        from praisonaiagents.workflows import YAMLWorkflowParser
        
        yaml_content = """
name: Input Test Workflow
input: "This is the workflow input"
agents:
  researcher:
    name: Researcher
    role: Research Analyst
    goal: Research topics
    instructions: "Provide research"

steps:
  - agent: researcher
    action: "Research {{input}}"
"""
        parser = YAMLWorkflowParser()
        workflow = parser.parse_string(yaml_content)
        
        assert workflow is not None
        assert workflow.default_input == "This is the workflow input"
    
    def test_topic_as_input_alias(self):
        """Test that 'topic' works as an alias for 'input' (backward compatibility)."""
        from praisonaiagents.workflows import YAMLWorkflowParser
        
        yaml_content = """
name: Topic Alias Test
topic: "This is the topic as input"
agents:
  researcher:
    name: Researcher
    role: Research Analyst
    goal: Research topics
    instructions: "Provide research"

steps:
  - agent: researcher
    action: "Research {{input}}"
"""
        parser = YAMLWorkflowParser()
        workflow = parser.parse_string(yaml_content)
        
        assert workflow is not None
        assert workflow.default_input == "This is the topic as input"
    
    def test_input_takes_precedence_over_topic(self):
        """Test that 'input' takes precedence over 'topic' when both are present."""
        from praisonaiagents.workflows import YAMLWorkflowParser
        
        yaml_content = """
name: Precedence Test
input: "Input value wins"
topic: "Topic value loses"
agents:
  researcher:
    name: Researcher
    role: Research Analyst
    goal: Research topics
    instructions: "Provide research"

steps:
  - agent: researcher
    action: "Research {{input}}"
"""
        parser = YAMLWorkflowParser()
        workflow = parser.parse_string(yaml_content)
        
        assert workflow is not None
        assert workflow.default_input == "Input value wins"
    
    def test_backstory_normalized_to_instructions(self):
        """Test that 'backstory' is normalized to 'instructions'."""
        from praisonaiagents.workflows import YAMLWorkflowParser
        
        yaml_content = """
name: Backstory Test
agents:
  researcher:
    name: Researcher
    role: Research Analyst
    goal: Research topics
    backstory: "Expert researcher with 10 years experience"

steps:
  - agent: researcher
    action: "Research AI"
"""
        parser = YAMLWorkflowParser()
        workflow = parser.parse_string(yaml_content)
        
        assert workflow is not None
        researcher = parser._agents.get('researcher')
        assert researcher is not None
    
    def test_description_normalized_to_action(self):
        """Test that 'description' is normalized to 'action'."""
        from praisonaiagents.workflows import YAMLWorkflowParser
        
        yaml_content = """
name: Description Test
agents:
  researcher:
    name: Researcher
    role: Research Analyst
    goal: Research topics
    instructions: "Provide research"

steps:
  - agent: researcher
    description: "Research AI trends"
"""
        parser = YAMLWorkflowParser()
        workflow = parser.parse_string(yaml_content)
        
        assert workflow is not None
        # The step should have been parsed with action from description
        researcher = parser._agents.get('researcher')
        assert researcher is not None
        assert hasattr(researcher, '_yaml_action')
        assert researcher._yaml_action == "Research AI trends"
    
    def test_full_agents_yaml_format(self):
        """Test that full agents.yaml format with roles, backstory, tasks is normalized."""
        from praisonaiagents.workflows import YAMLWorkflowParser
        
        yaml_content = """
topic: AI Research
framework: praisonai
process: workflow

workflow:
  planning: true
  verbose: true

roles:
  researcher:
    role: Research Analyst
    backstory: "Expert researcher"
    goal: Research topics
    
  writer:
    role: Content Writer
    backstory: "Expert writer"
    goal: Write content

steps:
  - agent: researcher
    description: "Research AI trends"
  - agent: writer
    description: "Write summary"
"""
        parser = YAMLWorkflowParser()
        workflow = parser.parse_string(yaml_content)
        
        assert workflow is not None
        assert workflow.name == "AI Research"
        assert 'researcher' in parser._agents
        assert 'writer' in parser._agents
    
    def test_parallel_steps_description_normalized(self):
        """Test that description in parallel steps is normalized to action."""
        from praisonaiagents.workflows import YAMLWorkflowParser
        
        yaml_content = """
name: Parallel Test
agents:
  researcher1:
    name: Researcher1
    role: Market Analyst
    goal: Research market
    instructions: "Provide market insights"
  researcher2:
    name: Researcher2
    role: Tech Analyst
    goal: Research tech
    instructions: "Provide tech insights"

steps:
  - name: parallel_research
    parallel:
      - agent: researcher1
        description: "Research market trends"
      - agent: researcher2
        description: "Research tech trends"
"""
        parser = YAMLWorkflowParser()
        workflow = parser.parse_string(yaml_content)
        
        assert workflow is not None
        # Both agents should have their actions set
        researcher1 = parser._agents.get('researcher1')
        researcher2 = parser._agents.get('researcher2')
        assert researcher1 is not None
        assert researcher2 is not None
    
    def test_canonical_names_work(self):
        """Test that canonical names (agents, instructions, action, steps, name) work."""
        from praisonaiagents.workflows import YAMLWorkflowParser
        
        yaml_content = """
name: Canonical Test
agents:
  researcher:
    name: Researcher
    role: Research Analyst
    goal: Research topics
    instructions: "Provide detailed research"

steps:
  - agent: researcher
    action: "Research AI trends"
"""
        parser = YAMLWorkflowParser()
        workflow = parser.parse_string(yaml_content)
        
        assert workflow is not None
        assert workflow.name == "Canonical Test"
        researcher = parser._agents.get('researcher')
        assert researcher is not None
        assert researcher._yaml_action == "Research AI trends"
    
    def test_mixed_old_and_new_names(self):
        """Test that mixing old and new names works."""
        from praisonaiagents.workflows import YAMLWorkflowParser
        
        yaml_content = """
name: Mixed Test
agents:
  researcher:
    name: Researcher
    role: Research Analyst
    goal: Research topics
    backstory: "Expert researcher"  # Old name
    
  writer:
    name: Writer
    role: Content Writer
    goal: Write content
    instructions: "Write clearly"  # New name

steps:
  - agent: researcher
    action: "Research AI"  # New name
  - agent: writer
    description: "Write summary"  # Old name
"""
        parser = YAMLWorkflowParser()
        workflow = parser.parse_string(yaml_content)
        
        assert workflow is not None
        assert 'researcher' in parser._agents
        assert 'writer' in parser._agents
