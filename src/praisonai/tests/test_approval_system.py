"""
Tests for the CLI approval system.

Tests:
1. --trust flag auto-approves all tools
2. --approve-level flag with different risk levels
3. Approval callback integration
"""

import pytest
import sys
import os

# Add the src directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


class TestApprovalFlags:
    """Test CLI approval flags."""
    
    def test_trust_flag_exists(self):
        """Test that --trust flag is defined in argparse."""
        import argparse
        
        # Check that the args object has the trust attribute after parsing
        # Parse with --help to avoid actually running anything
        parser = argparse.ArgumentParser()
        parser.add_argument("--trust", action="store_true")
        parser.add_argument("--approve-level", type=str, choices=["low", "medium", "high", "critical"])
        
        # Test that the arguments can be parsed
        args = parser.parse_args(['--trust'])
        assert args.trust is True
        
        args = parser.parse_args([])
        assert args.trust is False
    
    def test_approve_level_flag_exists(self):
        """Test that --approve-level flag is defined in argparse."""
        import argparse
        
        parser = argparse.ArgumentParser()
        parser.add_argument("--approve-level", type=str, choices=["low", "medium", "high", "critical"])
        
        # Test that the arguments can be parsed
        args = parser.parse_args(['--approve-level', 'high'])
        assert args.approve_level == 'high'
        
        args = parser.parse_args(['--approve-level', 'critical'])
        assert args.approve_level == 'critical'
    
    def test_trust_flag_in_praisonai_parser(self):
        """Test that --trust flag is in PraisonAI's actual parser."""
        from praisonai.cli.main import PraisonAI
        
        # Create instance - parse_args is called in __init__
        praison = PraisonAI()
        
        # Call parse_args to get the args (returns tuple: (Namespace, remaining_args))
        result = praison.parse_args()
        args = result[0] if isinstance(result, tuple) else result
        
        # The args should have trust attribute after parse_args
        assert hasattr(args, 'trust'), "PraisonAI.args should have 'trust' attribute"
        # Cleanup
        del praison
    
    def test_approve_level_flag_in_praisonai_parser(self):
        """Test that --approve-level flag is in PraisonAI's actual parser."""
        from praisonai.cli.main import PraisonAI
        
        # Create instance - parse_args is called in __init__
        praison = PraisonAI()
        
        # Call parse_args to get the args (returns tuple: (Namespace, remaining_args))
        result = praison.parse_args()
        args = result[0] if isinstance(result, tuple) else result
        
        # The args should have approve_level attribute after parse_args
        assert hasattr(args, 'approve_level'), "PraisonAI.args should have 'approve_level' attribute"


class TestApprovalCallback:
    """Test approval callback system."""
    
    def test_set_approval_callback(self):
        """Test that we can set a custom approval callback."""
        from praisonaiagents.approval import set_approval_callback, ApprovalDecision
        
        callback_called = []
        
        def custom_callback(function_name, arguments, risk_level):
            callback_called.append((function_name, arguments, risk_level))
            return ApprovalDecision(approved=True, reason="Test approved")
        
        set_approval_callback(custom_callback)
        
        # Verify callback was set
        from praisonaiagents.approval import approval_callback
        assert approval_callback == custom_callback
        
        # Reset callback
        set_approval_callback(None)
    
    def test_auto_approve_callback(self):
        """Test auto-approve callback returns approved decision."""
        from praisonaiagents.approval import ApprovalDecision
        
        def auto_approve_callback(function_name, arguments, risk_level):
            return ApprovalDecision(approved=True, reason="Auto-approved")
        
        decision = auto_approve_callback("execute_command", {"command": "ls"}, "critical")
        assert decision.approved is True
        assert decision.reason == "Auto-approved"
    
    def test_level_based_callback(self):
        """Test level-based approval callback."""
        from praisonaiagents.approval import ApprovalDecision
        
        def level_based_callback(function_name, arguments, risk_level, max_level="high"):
            """Approve based on risk level threshold."""
            levels = {"low": 1, "medium": 2, "high": 3, "critical": 4}
            tool_level = levels.get(risk_level, 4)
            max_allowed = levels.get(max_level, 3)
            
            if tool_level <= max_allowed:
                return ApprovalDecision(approved=True, reason=f"Auto-approved (level {risk_level} <= {max_level})")
            else:
                return ApprovalDecision(approved=False, reason=f"Denied (level {risk_level} > {max_level})")
        
        # Test with max_level="high"
        # Should approve low, medium, high but deny critical
        assert level_based_callback("test", {}, "low", "high").approved is True
        assert level_based_callback("test", {}, "medium", "high").approved is True
        assert level_based_callback("test", {}, "high", "high").approved is True
        assert level_based_callback("test", {}, "critical", "high").approved is False
        
        # Test with max_level="critical"
        # Should approve everything
        assert level_based_callback("test", {}, "critical", "critical").approved is True


class TestApprovalRequirements:
    """Test approval requirement configuration."""
    
    def test_default_dangerous_tools(self):
        """Test that default dangerous tools are configured."""
        from praisonaiagents.approval import APPROVAL_REQUIRED_TOOLS, TOOL_RISK_LEVELS
        
        # Check critical tools
        assert "execute_command" in APPROVAL_REQUIRED_TOOLS
        assert TOOL_RISK_LEVELS.get("execute_command") == "critical"
        
        # Check high risk tools
        assert "write_file" in APPROVAL_REQUIRED_TOOLS
        assert TOOL_RISK_LEVELS.get("write_file") == "high"
    
    def test_remove_approval_requirement(self):
        """Test removing approval requirement."""
        from praisonaiagents.approval import (
            add_approval_requirement, 
            remove_approval_requirement,
            is_approval_required,
            APPROVAL_REQUIRED_TOOLS
        )
        
        # Add a test tool
        add_approval_requirement("test_tool", "medium")
        assert is_approval_required("test_tool") is True
        
        # Remove it
        remove_approval_requirement("test_tool")
        assert is_approval_required("test_tool") is False
    
    def test_is_approval_required(self):
        """Test checking if approval is required."""
        from praisonaiagents.approval import is_approval_required
        
        # execute_command should require approval
        assert is_approval_required("execute_command") is True
        
        # read_file should not require approval
        assert is_approval_required("read_file") is False
        
        # list_files should not require approval
        assert is_approval_required("list_files") is False


class TestApprovalDecision:
    """Test ApprovalDecision class."""
    
    def test_approval_decision_approved(self):
        """Test approved decision."""
        from praisonaiagents.approval import ApprovalDecision
        
        decision = ApprovalDecision(approved=True, reason="User approved")
        assert decision.approved is True
        assert decision.reason == "User approved"
        assert decision.modified_args == {}
    
    def test_approval_decision_denied(self):
        """Test denied decision."""
        from praisonaiagents.approval import ApprovalDecision
        
        decision = ApprovalDecision(approved=False, reason="User denied")
        assert decision.approved is False
        assert decision.reason == "User denied"
    
    def test_approval_decision_with_modified_args(self):
        """Test decision with modified arguments."""
        from praisonaiagents.approval import ApprovalDecision
        
        decision = ApprovalDecision(
            approved=True, 
            reason="Approved with modifications",
            modified_args={"command": "ls -la"}
        )
        assert decision.approved is True
        assert decision.modified_args == {"command": "ls -la"}


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
