"""
Unit tests for Workflow output status/trace enablement.

Tests the DRY approach where Workflow uses the same OUTPUT_PRESETS as Agent.
"""



class TestWorkflowOutputDRY:
    """Test DRY approach - Workflow uses same presets as Agent."""
    
    def test_workflow_output_presets_is_output_presets(self):
        """WORKFLOW_OUTPUT_PRESETS should be identical to OUTPUT_PRESETS (DRY)."""
        from praisonaiagents.config.presets import OUTPUT_PRESETS, WORKFLOW_OUTPUT_PRESETS
        assert WORKFLOW_OUTPUT_PRESETS is OUTPUT_PRESETS, \
            "WORKFLOW_OUTPUT_PRESETS should be alias to OUTPUT_PRESETS for DRY"
    
    def test_workflow_output_config_is_output_config(self):
        """WorkflowOutputConfig should be identical to OutputConfig (DRY)."""
        from praisonaiagents.workflows import WorkflowOutputConfig
        from praisonaiagents.config.feature_configs import OutputConfig
        assert WorkflowOutputConfig is OutputConfig, \
            "WorkflowOutputConfig should be alias to OutputConfig for DRY"


class TestWorkflowOutputStatusEnablement:
    """Test that Workflow enables status/trace output when configured."""
    
    def test_workflow_status_preset_has_actions_trace(self):
        """Workflow with output='status' should have actions_trace=True."""
        from praisonaiagents import Workflow
        w = Workflow(name="test", steps=[], output="status")
        assert w._output_config is not None
        assert getattr(w._output_config, 'actions_trace', False) is True
    
    def test_workflow_trace_preset_has_status_trace(self):
        """Workflow with output='trace' should have status_trace=True."""
        from praisonaiagents import Workflow
        w = Workflow(name="test", steps=[], output="trace")
        assert w._output_config is not None
        assert getattr(w._output_config, 'status_trace', False) is True
    
    def test_workflow_status_enables_status_output(self):
        """Workflow with output='status' should enable status output."""
        from praisonaiagents.output.status import disable_status_output, is_status_output_enabled
        from praisonaiagents.output.trace import disable_trace_output
        
        # Reset state
        disable_status_output()
        disable_trace_output()
        
        from praisonaiagents import Workflow
        _w = Workflow(name="test", steps=[], output="status")
        
        assert is_status_output_enabled(), \
            "Status output should be enabled after Workflow(output='status')"
    
    def test_workflow_trace_enables_trace_output(self):
        """Workflow with output='trace' should enable trace output."""
        from praisonaiagents.output.status import disable_status_output
        from praisonaiagents.output.trace import disable_trace_output, is_trace_output_enabled
        
        # Reset state
        disable_status_output()
        disable_trace_output()
        
        from praisonaiagents import Workflow
        _w = Workflow(name="test", steps=[], output="trace")
        
        assert is_trace_output_enabled(), \
            "Trace output should be enabled after Workflow(output='trace')"
    
    def test_workflow_silent_does_not_enable_output(self):
        """Workflow with output='silent' should not enable any output."""
        from praisonaiagents.output.status import disable_status_output, is_status_output_enabled
        from praisonaiagents.output.trace import disable_trace_output, is_trace_output_enabled
        
        # Reset state
        disable_status_output()
        disable_trace_output()
        
        from praisonaiagents import Workflow
        _w = Workflow(name="test", steps=[], output="silent")
        
        assert not is_status_output_enabled(), \
            "Status output should NOT be enabled for output='silent'"
        assert not is_trace_output_enabled(), \
            "Trace output should NOT be enabled for output='silent'"


class TestWorkflowOutputPropagation:
    """Test that output config is propagated to child agents."""
    
    def test_workflow_stores_output_config(self):
        """Workflow should store resolved output config in _output_config."""
        from praisonaiagents import Workflow
        w = Workflow(name="test", steps=[], output="status")
        assert w._output_config is not None
        assert hasattr(w._output_config, 'actions_trace')
    
    def test_workflow_output_param_preserved(self):
        """Workflow.output should preserve the original value for propagation."""
        from praisonaiagents import Workflow
        w = Workflow(name="test", steps=[], output="status")
        assert w.output == "status"


class TestYAMLOutputParsing:
    """Test that YAML workflow.output field is parsed correctly."""
    
    def test_yaml_parser_parses_output_field(self):
        """YAMLWorkflowParser should parse workflow.output field."""
        from praisonaiagents.workflows.yaml_parser import YAMLWorkflowParser
        
        yaml_content = """
name: Test Workflow
workflow:
  output: status
  planning: false
steps: []
"""
        parser = YAMLWorkflowParser()
        workflow = parser.parse_string(yaml_content)
        
        assert workflow.output == "status", \
            "YAML workflow.output should be parsed and passed to Workflow"
    
    def test_yaml_parser_verbose_fallback(self):
        """YAMLWorkflowParser should use verbose flag as fallback for output."""
        from praisonaiagents.workflows.yaml_parser import YAMLWorkflowParser
        
        yaml_content = """
name: Test Workflow
workflow:
  verbose: true
steps: []
"""
        parser = YAMLWorkflowParser()
        workflow = parser.parse_string(yaml_content)
        
        assert workflow.output == "verbose", \
            "YAML workflow.verbose=true should set output='verbose'"
    
    def test_yaml_parser_output_takes_precedence(self):
        """YAMLWorkflowParser output should take precedence over verbose."""
        from praisonaiagents.workflows.yaml_parser import YAMLWorkflowParser
        
        yaml_content = """
name: Test Workflow
workflow:
  output: status
  verbose: true
steps: []
"""
        parser = YAMLWorkflowParser()
        workflow = parser.parse_string(yaml_content)
        
        assert workflow.output == "status", \
            "YAML workflow.output should take precedence over verbose"
