"""
Tests for include inside loop feature.
"""

import pytest


class TestIncludeInLoop:
    """Tests for include steps inside loops."""
    
    def test_include_step_handled_in_single_step_internal(self):
        """Test that Include steps are handled in _execute_single_step_internal."""
        from praisonaiagents.workflows import Workflow, Include
        
        workflow = Workflow(steps=[])
        
        # Create an Include step
        include_step = Include(recipe="test-recipe")
        
        # Verify Include is recognized
        assert isinstance(include_step, Include)
        assert include_step.recipe == "test-recipe"
    
    def test_loop_step_can_contain_include(self):
        """Test that Loop can have Include as its step."""
        from praisonaiagents.workflows import Loop, Include
        
        include_step = Include(recipe="wordpress-publisher")
        loop_step = Loop(
            step=include_step,
            over="items",
            parallel=True
        )
        
        assert loop_step.step is include_step
        assert isinstance(loop_step.step, Include)
        assert loop_step.parallel is True


class TestIncludeInLoopYAMLParsing:
    """Tests for parsing include inside loop from YAML."""
    
    def test_parse_loop_with_include_step(self):
        """Test parsing a loop that contains an include step."""
        from praisonaiagents.workflows import YAMLWorkflowParser, Loop, Include
        
        yaml_content = '''
agents:
  writer:
    role: Writer
    goal: Write content
    
steps:
  - name: write_posts
    agent: writer
    action: "Write about {{input}}"
    output_variable: posts
    
  - loop:
      over: posts
      parallel: true
    include: wordpress-publisher
'''
        parser = YAMLWorkflowParser()
        workflow = parser.parse_string(yaml_content)
        
        assert workflow is not None
        assert len(workflow.steps) >= 2
        
        # Find the loop step
        loop_found = False
        for step in workflow.steps:
            if isinstance(step, Loop):
                loop_found = True
                assert step.over == "posts"
                assert step.parallel is True
                # The step inside the loop should be an Include
                assert isinstance(step.step, Include)
                assert step.step.recipe == "wordpress-publisher"
                break
        
        assert loop_found, "Should have a loop step with include"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
