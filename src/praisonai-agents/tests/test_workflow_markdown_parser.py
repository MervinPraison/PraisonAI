"""
Test suite for Workflow Markdown Parser.

Tests the enhanced markdown parser for parsing agent config, tools,
context_from, and other new fields from workflow markdown files.
"""

import pytest
import tempfile
import os
import sys

# Add the package to path for testing
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from praisonaiagents import Workflow, Task
from praisonaiagents.workflows import WorkflowManager


class TestParseAgentConfig:
    """Test parsing agent configuration from markdown."""
    
    def test_parse_agent_config_block(self):
        """Should parse agent config from ```agent block."""
        manager = WorkflowManager()
        
        body = '''
## Step 1: Research
Research the topic.

```agent
role: Researcher
goal: Find comprehensive information
backstory: Expert researcher with 10 years experience
llm: gpt-4o
```

```action
Search for information about AI
```
'''
        steps = manager._parse_steps(body)
        
        assert len(steps) == 1
        assert steps[0].agent_config is not None
        assert steps[0].agent_config["role"] == "Researcher"
        assert steps[0].agent_config["goal"] == "Find comprehensive information"
        assert steps[0].agent_config["llm"] == "gpt-4o"
    
    def test_parse_agent_config_helper(self):
        """_parse_agent_config should parse key-value pairs."""
        manager = WorkflowManager()
        
        agent_str = '''
role: Writer
goal: Write engaging content
verbose: true
max_iter: 10
'''
        config = manager._parse_agent_config(agent_str)
        
        assert config["role"] == "Writer"
        assert config["goal"] == "Write engaging content"
        assert config["verbose"] is True
        assert config["max_iter"] == 10


class TestParseToolsBlock:
    """Test parsing tools from markdown."""
    
    def test_parse_tools_block(self):
        """Should parse tools from ```tools block."""
        manager = WorkflowManager()
        
        body = '''
## Step 1: Search
Search for information.

```tools
tavily_search
web_browser
calculator
```

```action
Search for AI trends
```
'''
        steps = manager._parse_steps(body)
        
        assert len(steps) == 1
        assert steps[0].tools is not None
        assert len(steps[0].tools) == 3
        assert "tavily_search" in steps[0].tools
        assert "web_browser" in steps[0].tools
        assert "calculator" in steps[0].tools


class TestParseContextFrom:
    """Test parsing context_from from markdown."""
    
    def test_parse_context_from(self):
        """Should parse context_from directive."""
        manager = WorkflowManager()
        
        body = '''
## Step 1: Research
Research the topic.

```action
Research AI
```

## Step 2: Analyze
Analyze the research.

```action
Analyze data
```

## Step 3: Summary
Summarize findings.

context_from: [Research, Analyze]

```action
Write summary
```
'''
        steps = manager._parse_steps(body)
        
        assert len(steps) == 3
        assert steps[2].context_from is not None
        assert "Research" in steps[2].context_from
        assert "Analyze" in steps[2].context_from


class TestParseRetainFullContext:
    """Test parsing retain_full_context from markdown."""
    
    def test_parse_retain_full_context_false(self):
        """Should parse retain_full_context: false."""
        manager = WorkflowManager()
        
        body = '''
## Step 1: Process
Process data.

retain_full_context: false

```action
Process the data
```
'''
        steps = manager._parse_steps(body)
        
        assert len(steps) == 1
        assert steps[0].retain_full_context is False
    
    def test_parse_retain_full_context_true(self):
        """Should parse retain_full_context: true."""
        manager = WorkflowManager()
        
        body = '''
## Step 1: Process
Process data.

retain_full_context: true

```action
Process the data
```
'''
        steps = manager._parse_steps(body)
        
        assert len(steps) == 1
        assert steps[0].retain_full_context is True
    
    def test_retain_full_context_default_true(self):
        """retain_full_context should default to True."""
        manager = WorkflowManager()
        
        body = '''
## Step 1: Process
Process data.

```action
Process the data
```
'''
        steps = manager._parse_steps(body)
        
        assert len(steps) == 1
        assert steps[0].retain_full_context is True


class TestParseOutputVariable:
    """Test parsing output_variable from markdown."""
    
    def test_parse_output_variable(self):
        """Should parse output_variable directive."""
        manager = WorkflowManager()
        
        body = '''
## Step 1: Generate
Generate report.

output_variable: report_data

```action
Generate the report
```
'''
        steps = manager._parse_steps(body)
        
        assert len(steps) == 1
        assert steps[0].output_variable == "report_data"


class TestLoadWorkflowWithNewFields:
    """Test loading workflow files with new fields."""
    
    def test_load_workflow_with_default_llm(self):
        """Should load workflow with default_llm from frontmatter."""
        manager = WorkflowManager()
        
        content = '''---
name: Test Workflow
description: A test workflow
default_llm: gpt-4o
planning: true
planning_llm: gpt-4o-mini
---

## Step 1: Test
Test step.

```action
Do something
```
'''
        # Create temp file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
            f.write(content)
            temp_path = f.name
        
        try:
            from pathlib import Path
            workflow = manager._load_workflow(Path(temp_path))
            
            assert workflow is not None
            assert workflow.default_llm == "gpt-4o"
            # Planning is now a config object, check _planning_enabled
            assert workflow._planning_enabled is True
            assert workflow._planning_llm == "gpt-4o-mini"
        finally:
            os.unlink(temp_path)


class TestCompleteWorkflowParsing:
    """Test complete workflow parsing with all new features."""
    
    def test_parse_complete_workflow(self):
        """Should parse a complete workflow with all new features."""
        manager = WorkflowManager()
        
        body = '''
## Step 1: Research
Research the topic thoroughly.

```agent
role: Researcher
goal: Find comprehensive information
backstory: Expert researcher
```

```tools
tavily_search
web_browser
```

output_variable: research_data

```action
Search for information about {{topic}}
```

## Step 2: Analyze
Analyze the research findings.

```agent
role: Analyst
goal: Analyze data patterns
```

context_from: [Research]
retain_full_context: false

```action
Analyze: {{research_data}}
```

## Step 3: Write
Write the final report.

```agent
role: Writer
goal: Write engaging content
```

```action
Write report based on analysis
```
'''
        steps = manager._parse_steps(body)
        
        assert len(steps) == 3
        
        # Step 1
        assert steps[0].name == "Research"
        assert steps[0].agent_config is not None
        assert steps[0].agent_config["role"] == "Researcher"
        assert steps[0].tools is not None
        assert "tavily_search" in steps[0].tools
        assert steps[0].output_variable == "research_data"
        
        # Step 2
        assert steps[1].name == "Analyze"
        assert steps[1].agent_config["role"] == "Analyst"
        assert steps[1].context_from == ["Research"]
        assert steps[1].retain_full_context is False
        
        # Step 3
        assert steps[2].name == "Write"
        assert steps[2].agent_config["role"] == "Writer"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
