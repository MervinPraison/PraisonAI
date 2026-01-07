"""
Tests for the Permissions module.

TDD: Tests for pattern-based permissions, persistent approvals, and doom loop detection.
"""

import os
import shutil
import tempfile
import time

from praisonaiagents.permissions import (
    PermissionManager,
    PermissionRule,
    PermissionAction,
    PermissionResult,
    DoomLoopDetector,
)
from praisonaiagents.permissions.rules import PersistentApproval


class TestPermissionAction:
    """Tests for PermissionAction enum."""
    
    def test_action_values(self):
        """Test action enum values."""
        assert PermissionAction.ALLOW.value == "allow"
        assert PermissionAction.DENY.value == "deny"
        assert PermissionAction.ASK.value == "ask"


class TestPermissionRule:
    """Tests for PermissionRule."""
    
    def test_rule_creation(self):
        """Test basic rule creation."""
        rule = PermissionRule(
            pattern="bash:*",
            action=PermissionAction.ASK,
            description="Require approval for bash"
        )
        
        assert rule.pattern == "bash:*"
        assert rule.action == PermissionAction.ASK
        assert rule.description == "Require approval for bash"
    
    def test_rule_glob_matching(self):
        """Test glob pattern matching."""
        rule = PermissionRule(pattern="bash:rm *")
        
        assert rule.matches("bash:rm -rf /tmp") is True
        assert rule.matches("bash:ls -la") is False
        assert rule.matches("read:file.txt") is False
    
    def test_rule_wildcard_matching(self):
        """Test wildcard pattern matching."""
        rule = PermissionRule(pattern="*:*")
        
        assert rule.matches("bash:anything") is True
        assert rule.matches("read:file.txt") is True
    
    def test_rule_regex_matching(self):
        """Test regex pattern matching."""
        rule = PermissionRule(
            pattern=r"bash:rm\s+-rf\s+.*",
            is_regex=True
        )
        
        assert rule.matches("bash:rm -rf /tmp") is True
        assert rule.matches("bash:rm /tmp") is False
    
    def test_rule_disabled(self):
        """Test disabled rule doesn't match."""
        rule = PermissionRule(pattern="*", enabled=False)
        
        assert rule.matches("anything") is False
    
    def test_rule_serialization(self):
        """Test rule round-trip."""
        rule = PermissionRule(
            pattern="bash:*",
            action=PermissionAction.DENY,
            description="Test",
            priority=10
        )
        
        d = rule.to_dict()
        restored = PermissionRule.from_dict(d)
        
        assert restored.pattern == rule.pattern
        assert restored.action == rule.action
        assert restored.priority == rule.priority


class TestPermissionResult:
    """Tests for PermissionResult."""
    
    def test_result_allowed(self):
        """Test allowed result."""
        result = PermissionResult(
            action=PermissionAction.ALLOW,
            target="read:file.txt"
        )
        
        assert result.is_allowed is True
        assert result.is_denied is False
        assert result.needs_approval is False
    
    def test_result_denied(self):
        """Test denied result."""
        result = PermissionResult(
            action=PermissionAction.DENY,
            target="bash:rm -rf /"
        )
        
        assert result.is_allowed is False
        assert result.is_denied is True
        assert result.needs_approval is False
    
    def test_result_ask_pending(self):
        """Test ask result pending approval."""
        result = PermissionResult(
            action=PermissionAction.ASK,
            target="bash:ls"
        )
        
        assert result.is_allowed is False
        assert result.is_denied is False
        assert result.needs_approval is True
    
    def test_result_ask_approved(self):
        """Test ask result after approval."""
        result = PermissionResult(
            action=PermissionAction.ASK,
            target="bash:ls",
            approved=True
        )
        
        assert result.is_allowed is True
        assert result.needs_approval is False
    
    def test_result_ask_rejected(self):
        """Test ask result after rejection."""
        result = PermissionResult(
            action=PermissionAction.ASK,
            target="bash:ls",
            approved=False
        )
        
        assert result.is_denied is True
        assert result.needs_approval is False


class TestPersistentApproval:
    """Tests for PersistentApproval."""
    
    def test_approval_creation(self):
        """Test approval creation."""
        approval = PersistentApproval(
            pattern="bash:ls *",
            approved=True,
            scope="always"
        )
        
        assert approval.pattern == "bash:ls *"
        assert approval.approved is True
        assert approval.scope == "always"
    
    def test_approval_matching(self):
        """Test approval pattern matching."""
        approval = PersistentApproval(pattern="bash:ls *", approved=True)
        
        assert approval.matches("bash:ls -la") is True
        assert approval.matches("bash:rm file") is False
    
    def test_approval_expired(self):
        """Test expired approval."""
        approval = PersistentApproval(
            pattern="*",
            approved=True,
            expires_at=time.time() - 100  # Expired
        )
        
        assert approval.is_valid() is False
        assert approval.matches("anything") is False
    
    def test_approval_agent_filter(self):
        """Test approval agent filtering."""
        approval = PersistentApproval(
            pattern="*",
            approved=True,
            agent_name="agent_1"
        )
        
        assert approval.matches("anything", agent_name="agent_1") is True
        assert approval.matches("anything", agent_name="agent_2") is False


class TestDoomLoopDetector:
    """Tests for DoomLoopDetector."""
    
    def test_detector_creation(self):
        """Test detector creation."""
        detector = DoomLoopDetector()
        
        assert detector.loop_threshold == 3
        assert detector.window_seconds == 60
    
    def test_detector_no_loop(self):
        """Test no loop detected for varied calls."""
        detector = DoomLoopDetector()
        
        detector.record("bash", {"command": "ls"})
        detector.record("bash", {"command": "pwd"})
        detector.record("read", {"file": "test.txt"})
        
        result = detector.check("bash", {"command": "cat file"})
        
        assert result.is_loop is False
    
    def test_detector_loop_detected(self):
        """Test loop detection for identical calls."""
        detector = DoomLoopDetector(loop_threshold=3)
        
        detector.record("bash", {"command": "ls"})
        detector.record("bash", {"command": "ls"})
        detector.record("bash", {"command": "ls"})
        
        result = detector.check("bash", {"command": "ls"})
        
        assert result.is_loop is True
        assert result.loop_count >= 3
        assert "bash" in result.reason
    
    def test_detector_record_and_check(self):
        """Test combined record and check."""
        detector = DoomLoopDetector(loop_threshold=2)
        
        result1 = detector.record_and_check("bash", {"command": "ls"})
        assert result1.is_loop is False
        
        # Second call - now we have 1 record, checking finds 1, records another
        result2 = detector.record_and_check("bash", {"command": "ls"})
        assert result2.is_loop is False  # Still only 1 in history when checked
        
        # Third call - now we have 2 records, checking finds 2 >= threshold
        result3 = detector.record_and_check("bash", {"command": "ls"})
        assert result3.is_loop is True
    
    def test_detector_reset(self):
        """Test resetting detector."""
        detector = DoomLoopDetector(loop_threshold=2)
        
        detector.record("bash", {"command": "ls"})
        detector.record("bash", {"command": "ls"})
        
        detector.reset()
        
        result = detector.check("bash", {"command": "ls"})
        assert result.is_loop is False
    
    def test_detector_reset_tool(self):
        """Test resetting specific tool."""
        detector = DoomLoopDetector(loop_threshold=2)
        
        detector.record("bash", {"command": "ls"})
        detector.record("bash", {"command": "ls"})
        detector.record("read", {"file": "test.txt"})
        
        detector.reset_tool("bash")
        
        result = detector.check("bash", {"command": "ls"})
        assert result.is_loop is False
        
        # read should still have its record
        stats = detector.get_stats()
        assert stats["total_calls"] == 1
    
    def test_detector_stats(self):
        """Test getting stats."""
        detector = DoomLoopDetector()
        
        detector.record("bash", {"command": "ls"})
        detector.record("bash", {"command": "pwd"})
        detector.record("read", {"file": "test.txt"})
        
        stats = detector.get_stats()
        
        assert stats["total_calls"] == 3
        assert stats["unique_tools"] == 2


class TestPermissionManager:
    """Tests for PermissionManager."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.manager = PermissionManager(storage_dir=self.temp_dir)
    
    def teardown_method(self):
        """Clean up test fixtures."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_manager_creation(self):
        """Test manager creation."""
        assert self.manager is not None
    
    def test_add_rule(self):
        """Test adding a rule."""
        rule_id = self.manager.add_rule(PermissionRule(
            pattern="bash:*",
            action=PermissionAction.ASK
        ))
        
        assert rule_id is not None
        rules = self.manager.get_rules()
        assert len(rules) == 1
    
    def test_remove_rule(self):
        """Test removing a rule."""
        rule_id = self.manager.add_rule(PermissionRule(pattern="*"))
        
        result = self.manager.remove_rule(rule_id)
        
        assert result is True
        assert len(self.manager.get_rules()) == 0
    
    def test_check_allow(self):
        """Test checking allowed action."""
        self.manager.add_rule(PermissionRule(
            pattern="read:*",
            action=PermissionAction.ALLOW
        ))
        
        result = self.manager.check("read:file.txt")
        
        assert result.action == PermissionAction.ALLOW
        assert result.is_allowed is True
    
    def test_check_deny(self):
        """Test checking denied action."""
        self.manager.add_rule(PermissionRule(
            pattern="bash:rm *",
            action=PermissionAction.DENY
        ))
        
        result = self.manager.check("bash:rm -rf /")
        
        assert result.action == PermissionAction.DENY
        assert result.is_denied is True
    
    def test_check_ask(self):
        """Test checking ask action."""
        self.manager.add_rule(PermissionRule(
            pattern="bash:*",
            action=PermissionAction.ASK
        ))
        
        result = self.manager.check("bash:ls")
        
        assert result.action == PermissionAction.ASK
        assert result.needs_approval is True
    
    def test_check_default_ask(self):
        """Test default action is ask."""
        result = self.manager.check("unknown:action")
        
        assert result.action == PermissionAction.ASK
    
    def test_rule_priority(self):
        """Test rule priority ordering."""
        self.manager.add_rule(PermissionRule(
            pattern="bash:*",
            action=PermissionAction.ASK,
            priority=1
        ))
        self.manager.add_rule(PermissionRule(
            pattern="bash:ls *",
            action=PermissionAction.ALLOW,
            priority=10  # Higher priority
        ))
        
        result = self.manager.check("bash:ls -la")
        
        assert result.action == PermissionAction.ALLOW
    
    def test_approve(self):
        """Test recording approval."""
        approval = self.manager.approve("bash:ls", approved=True, scope="always")
        
        assert approval.approved is True
        
        # Check that approval is used
        result = self.manager.check("bash:ls")
        assert result.is_allowed is True
    
    def test_approve_deny(self):
        """Test recording denial."""
        self.manager.approve("bash:rm *", approved=False, scope="always")
        
        result = self.manager.check("bash:rm file.txt")
        
        assert result.is_denied is True
    
    def test_check_and_approve_with_callback(self):
        """Test check and approve with callback."""
        approvals = []
        
        def callback(target, reason):
            approvals.append(target)
            return True
        
        self.manager.set_approval_callback(callback)
        
        result = self.manager.check_and_approve("bash:ls")
        
        assert len(approvals) == 1
        assert result.approved is True
    
    def test_clear_approvals(self):
        """Test clearing approvals."""
        self.manager.approve("bash:*", approved=True, scope="always")
        
        self.manager.clear_approvals()
        
        result = self.manager.check("bash:ls")
        assert result.needs_approval is True
    
    def test_doom_loop_integration(self):
        """Test doom loop detection integration."""
        result = self.manager.check_doom_loop("bash", {"command": "ls"})
        
        assert result.is_loop is False
    
    def test_persistence(self):
        """Test rules persist across instances."""
        self.manager.add_rule(PermissionRule(
            pattern="read:*",
            action=PermissionAction.ALLOW
        ))
        
        # Create new manager with same storage
        manager2 = PermissionManager(storage_dir=self.temp_dir)
        
        rules = manager2.get_rules()
        assert len(rules) == 1
        assert rules[0].pattern == "read:*"
    
    def test_agent_filter(self):
        """Test agent-specific rules."""
        self.manager.add_rule(PermissionRule(
            pattern="bash:*",
            action=PermissionAction.ALLOW,
            agent_name="agent_1"
        ))
        self.manager.add_rule(PermissionRule(
            pattern="bash:*",
            action=PermissionAction.DENY,
            agent_name="agent_2"
        ))
        
        result1 = self.manager.check("bash:ls", agent_name="agent_1")
        result2 = self.manager.check("bash:ls", agent_name="agent_2")
        
        assert result1.action == PermissionAction.ALLOW
        assert result2.action == PermissionAction.DENY
    
    def test_to_dict(self):
        """Test exporting manager state."""
        self.manager.add_rule(PermissionRule(pattern="*"))
        self.manager.approve("bash:*", approved=True)
        
        data = self.manager.to_dict()
        
        assert len(data["rules"]) == 1
        assert len(data["approvals"]) == 1
