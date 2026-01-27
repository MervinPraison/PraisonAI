"""
Tests for YAML-based and environment variable auto-approval of dangerous tools.

These tests verify that:
1. Tools can be auto-approved via YAML 'approve' field
2. Tools can be auto-approved via PRAISONAI_AUTO_APPROVE env var
3. The approval context is properly set and reset during workflow execution
"""

import os
import pytest
from unittest.mock import patch, MagicMock

from praisonaiagents.approval import (
    is_yaml_approved,
    is_env_auto_approve,
    set_yaml_approved_tools,
    reset_yaml_approved_tools,
    require_approval,
    is_already_approved,
    mark_approved,
    clear_approval_context,
)


class TestYAMLApproval:
    """Tests for YAML-based tool auto-approval."""
    
    def test_is_yaml_approved_returns_false_when_not_set(self):
        """Tool should not be approved when no YAML approval is set."""
        assert is_yaml_approved("write_file") is False
        assert is_yaml_approved("delete_file") is False
    
    def test_set_yaml_approved_tools_makes_tools_approved(self):
        """Setting YAML-approved tools should make them approved."""
        token = set_yaml_approved_tools(["write_file", "delete_file"])
        try:
            assert is_yaml_approved("write_file") is True
            assert is_yaml_approved("delete_file") is True
            assert is_yaml_approved("read_file") is False  # Not in list
        finally:
            reset_yaml_approved_tools(token)
    
    def test_reset_yaml_approved_tools_clears_approval(self):
        """Resetting YAML-approved tools should clear approval."""
        token = set_yaml_approved_tools(["write_file"])
        assert is_yaml_approved("write_file") is True
        
        reset_yaml_approved_tools(token)
        assert is_yaml_approved("write_file") is False
    
    def test_yaml_approval_is_context_isolated(self):
        """YAML approval should be isolated to the current context."""
        # Set approval in one context
        token = set_yaml_approved_tools(["write_file"])
        assert is_yaml_approved("write_file") is True
        
        # Reset should restore previous state
        reset_yaml_approved_tools(token)
        assert is_yaml_approved("write_file") is False


class TestEnvVarApproval:
    """Tests for environment variable auto-approval."""
    
    def test_is_env_auto_approve_returns_false_when_not_set(self):
        """Should return False when env var is not set."""
        with patch.dict(os.environ, {}, clear=True):
            # Ensure the var is not set
            os.environ.pop("PRAISONAI_AUTO_APPROVE", None)
            assert is_env_auto_approve() is False
    
    def test_is_env_auto_approve_returns_true_for_true(self):
        """Should return True when env var is 'true'."""
        with patch.dict(os.environ, {"PRAISONAI_AUTO_APPROVE": "true"}):
            assert is_env_auto_approve() is True
    
    def test_is_env_auto_approve_returns_true_for_1(self):
        """Should return True when env var is '1'."""
        with patch.dict(os.environ, {"PRAISONAI_AUTO_APPROVE": "1"}):
            assert is_env_auto_approve() is True
    
    def test_is_env_auto_approve_returns_true_for_yes(self):
        """Should return True when env var is 'yes'."""
        with patch.dict(os.environ, {"PRAISONAI_AUTO_APPROVE": "yes"}):
            assert is_env_auto_approve() is True
    
    def test_is_env_auto_approve_returns_false_for_false(self):
        """Should return False when env var is 'false'."""
        with patch.dict(os.environ, {"PRAISONAI_AUTO_APPROVE": "false"}):
            assert is_env_auto_approve() is False
    
    def test_is_env_auto_approve_case_insensitive(self):
        """Should be case-insensitive."""
        with patch.dict(os.environ, {"PRAISONAI_AUTO_APPROVE": "TRUE"}):
            assert is_env_auto_approve() is True
        with patch.dict(os.environ, {"PRAISONAI_AUTO_APPROVE": "True"}):
            assert is_env_auto_approve() is True


class TestRequireApprovalDecorator:
    """Tests for the @require_approval decorator with auto-approval."""
    
    def setup_method(self):
        """Clear approval context before each test."""
        clear_approval_context()
    
    def test_yaml_approved_tool_executes_without_prompt(self):
        """Tool should execute without prompting when YAML-approved."""
        @require_approval(risk_level="high")
        def dangerous_tool(data: str) -> str:
            return f"Executed with: {data}"
        
        # Set YAML approval
        token = set_yaml_approved_tools(["dangerous_tool"])
        try:
            # Should execute without prompting
            result = dangerous_tool("test data")
            assert result == "Executed with: test data"
        finally:
            reset_yaml_approved_tools(token)
    
    def test_env_approved_tool_executes_without_prompt(self):
        """Tool should execute without prompting when env var is set."""
        @require_approval(risk_level="high")
        def another_dangerous_tool(data: str) -> str:
            return f"Executed with: {data}"
        
        with patch.dict(os.environ, {"PRAISONAI_AUTO_APPROVE": "true"}):
            # Should execute without prompting
            result = another_dangerous_tool("test data")
            assert result == "Executed with: test data"
    
    def test_yaml_approval_takes_precedence_over_env(self):
        """YAML approval should work even if env var is not set."""
        @require_approval(risk_level="high")
        def yaml_approved_tool(data: str) -> str:
            return f"Executed with: {data}"
        
        # Ensure env var is not set
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("PRAISONAI_AUTO_APPROVE", None)
            
            # Set YAML approval
            token = set_yaml_approved_tools(["yaml_approved_tool"])
            try:
                result = yaml_approved_tool("test data")
                assert result == "Executed with: test data"
            finally:
                reset_yaml_approved_tools(token)


class TestYAMLParserApproveField:
    """Tests for YAML parser handling of 'approve' field."""
    
    def test_yaml_parser_extracts_approve_field(self):
        """YAML parser should extract approve field from workflow config."""
        from praisonaiagents.workflows.yaml_parser import YAMLWorkflowParser
        
        yaml_content = """
name: Test Workflow
approve:
  - write_file
  - delete_file
agents:
  researcher:
    role: Researcher
    instructions: Research topics
steps:
  - name: research
    agent: researcher
    action: Research AI
"""
        parser = YAMLWorkflowParser()
        workflow = parser.parse_string(yaml_content)
        
        # Check that approve_tools is set on the workflow
        assert hasattr(workflow, 'approve_tools')
        assert 'write_file' in workflow.approve_tools
        assert 'delete_file' in workflow.approve_tools
    
    def test_yaml_parser_handles_single_approve_tool(self):
        """YAML parser should handle single tool as string."""
        from praisonaiagents.workflows.yaml_parser import YAMLWorkflowParser
        
        yaml_content = """
name: Test Workflow
approve: write_file
agents:
  researcher:
    role: Researcher
    instructions: Research topics
steps:
  - name: research
    agent: researcher
    action: Research AI
"""
        parser = YAMLWorkflowParser()
        workflow = parser.parse_string(yaml_content)
        
        assert hasattr(workflow, 'approve_tools')
        assert 'write_file' in workflow.approve_tools
    
    def test_yaml_parser_handles_empty_approve(self):
        """YAML parser should handle missing approve field."""
        from praisonaiagents.workflows.yaml_parser import YAMLWorkflowParser
        
        yaml_content = """
name: Test Workflow
agents:
  researcher:
    role: Researcher
    instructions: Research topics
steps:
  - name: research
    agent: researcher
    action: Research AI
"""
        parser = YAMLWorkflowParser()
        workflow = parser.parse_string(yaml_content)
        
        assert hasattr(workflow, 'approve_tools')
        assert workflow.approve_tools == []
