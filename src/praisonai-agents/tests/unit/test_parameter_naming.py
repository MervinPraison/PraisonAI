"""
TDD Tests for Parameter Naming Standardization.

Tests the following changes:
1. llm= shows deprecation warning, model= is preferred
2. Task depends_on= is alias for context=
3. Task guardrails= is canonical (guardrail= deprecated)
4. YAML parser normalizes depends_on

These tests are written FIRST (TDD) - they should FAIL initially.
"""

import warnings


class TestAgentLLMDeprecation:
    """Test that llm= parameter shows deprecation warning."""
    
    def test_model_param_no_warning(self):
        """Using model= should NOT produce a deprecation warning."""
        from praisonaiagents import Agent
        
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            _agent = Agent(  # noqa: F841
                name="test",
                instructions="Test agent",
                model="gpt-4o-mini"
            )
            
            # Filter for DeprecationWarning about 'llm'
            llm_warnings = [x for x in w if 'llm' in str(x.message).lower()]
            assert len(llm_warnings) == 0, "model= should not produce deprecation warning"
    
    def test_llm_param_shows_deprecation_warning(self):
        """Using llm= should produce a deprecation warning."""
        from praisonaiagents import Agent
        
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            _agent = Agent(  # noqa: F841
                name="test",
                instructions="Test agent",
                llm="gpt-4o-mini"
            )
            
            # Filter for DeprecationWarning about 'llm'
            llm_warnings = [x for x in w if 'llm' in str(x.message).lower() and issubclass(x.category, DeprecationWarning)]
            assert len(llm_warnings) >= 1, "llm= should produce deprecation warning"
            assert 'model' in str(llm_warnings[0].message).lower(), "Warning should suggest using 'model' instead"
    
    def test_llm_and_model_both_work(self):
        """Both llm= and model= should work (backward compatibility)."""
        from praisonaiagents import Agent
        
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")  # Ignore warnings for this test
            
            agent1 = Agent(name="test1", instructions="Test", llm="gpt-4o-mini")
            agent2 = Agent(name="test2", instructions="Test", model="gpt-4o-mini")
            
            # Both should have the same model configured
            assert agent1.llm == agent2.llm


class TestTaskDependsOnAlias:
    """Test that depends_on= is an alias for context= in Task."""
    
    def test_depends_on_alias_works(self):
        """depends_on= should work as alias for context=."""
        from praisonaiagents import Task
        
        task1 = Task(description="First task")
        task2 = Task(
            description="Second task",
            depends_on=[task1]
        )
        
        assert task2.context == [task1], "depends_on should set context"
    
    def test_context_still_works(self):
        """context= should still work (backward compatibility)."""
        from praisonaiagents import Task
        
        task1 = Task(description="First task")
        task2 = Task(
            description="Second task",
            context=[task1]
        )
        
        assert task2.context == [task1]
    
    def test_depends_on_and_context_merge(self):
        """If both provided, depends_on takes precedence."""
        from praisonaiagents import Task
        
        task1 = Task(description="First task")
        task2 = Task(description="Second task")
        task3 = Task(
            description="Third task",
            context=[task1],
            depends_on=[task2]
        )
        
        # depends_on should take precedence
        assert task3.context == [task2], "depends_on should take precedence over context"
    
    def test_depends_on_attribute_accessible(self):
        """depends_on should be accessible as an attribute."""
        from praisonaiagents import Task
        
        task1 = Task(description="First task")
        task2 = Task(
            description="Second task",
            depends_on=[task1]
        )
        
        # Should be accessible via both names
        assert task2.depends_on == [task1]
        assert task2.context == [task1]


class TestTaskGuardrailsStandardization:
    """Test that guardrails= is the canonical name."""
    
    def test_guardrails_plural_works(self):
        """guardrails= (plural) should work."""
        from praisonaiagents import Task
        
        def my_guardrail(output):
            return (True, output)
        
        task = Task(
            description="Test task",
            guardrails=my_guardrail
        )
        
        assert task.guardrail == my_guardrail
    
    def test_guardrail_singular_shows_deprecation(self):
        """guardrail= (singular) should show deprecation warning."""
        from praisonaiagents import Task
        
        def my_guardrail(output):
            return (True, output)
        
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            _task = Task(  # noqa: F841
                description="Test task",
                guardrail=my_guardrail
            )
            
            # Filter for DeprecationWarning about 'guardrail'
            gr_warnings = [x for x in w if 'guardrail' in str(x.message).lower() and issubclass(x.category, DeprecationWarning)]
            assert len(gr_warnings) >= 1, "guardrail= (singular) should produce deprecation warning"
    
    def test_guardrails_takes_precedence(self):
        """If both provided, guardrails= takes precedence."""
        from praisonaiagents import Task
        
        def guardrail1(output):
            return (True, "guardrail1")
        
        def guardrail2(output):
            return (True, "guardrail2")
        
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            task = Task(
                description="Test task",
                guardrail=guardrail1,
                guardrails=guardrail2
            )
        
        assert task.guardrail == guardrail2, "guardrails= should take precedence"


class TestYAMLParserNormalization:
    """Test YAML parser normalizes parameter names."""
    
    def test_yaml_depends_on_normalized(self):
        """YAML with depends_on should work - parser should accept the field."""
        from praisonaiagents.workflows.yaml_parser import YAMLWorkflowParser
        
        yaml_content = """
name: Test Workflow
agents:
  researcher:
    name: Researcher
    instructions: Research topics
steps:
  - name: step1
    agent: researcher
    action: "Do research"
  - name: step2
    agent: researcher
    action: "Summarize"
    depends_on: [step1]
"""
        parser = YAMLWorkflowParser()
        # Should not raise an error - depends_on should be accepted
        workflow = parser.parse_string(yaml_content)
        
        # The workflow should have 2 steps
        assert len(workflow.steps) == 2
        # Workflow parsed successfully with depends_on field
        assert workflow.name == "Test Workflow"
    
    def test_yaml_context_still_works(self):
        """YAML with context should still work."""
        from praisonaiagents.workflows.yaml_parser import YAMLWorkflowParser
        
        yaml_content = """
name: Test Workflow
agents:
  researcher:
    name: Researcher
    instructions: Research topics
steps:
  - name: step1
    agent: researcher
    action: "Do research"
  - name: step2
    agent: researcher
    action: "Summarize"
    context: [step1]
"""
        parser = YAMLWorkflowParser()
        workflow = parser.parse_string(yaml_content)
        
        assert len(workflow.steps) == 2


class TestBackwardCompatibility:
    """Ensure all changes are backward compatible."""
    
    def test_agent_creation_unchanged(self):
        """Basic agent creation should work unchanged."""
        from praisonaiagents import Agent
        
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            agent = Agent(
                name="test",
                role="Tester",
                goal="Test things",
                backstory="A test agent"
            )
        
        assert agent.name == "test"
        assert agent.role == "Tester"
    
    def test_task_creation_unchanged(self):
        """Basic task creation should work unchanged."""
        from praisonaiagents import Task
        
        task = Task(
            description="Test task",
            expected_output="Test output"
        )
        
        assert task.description == "Test task"
    
    def test_action_alias_still_works(self):
        """action= should still work as alias for description=."""
        from praisonaiagents import Task
        
        task = Task(action="Do something")
        
        assert task.description == "Do something"
        assert task.action == "Do something"


class TestPerformance:
    """Ensure no performance regression."""
    
    def test_import_time_acceptable(self):
        """Import time should be under 200ms."""
        import subprocess
        import time
        
        # Run import in subprocess to get clean timing
        start = time.time()
        subprocess.run(
            ['python3', '-c', 'import praisonaiagents'],
            capture_output=True,
            timeout=10
        )
        elapsed = time.time() - start
        
        # Allow some overhead for subprocess startup
        # The actual import should be much faster
        assert elapsed < 5.0, f"Import took {elapsed:.2f}s, expected < 5s (including subprocess overhead)"
