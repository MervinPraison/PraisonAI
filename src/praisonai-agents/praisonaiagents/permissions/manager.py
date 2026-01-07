"""
Permission Manager for PraisonAI Agents.

Manages permission rules, persistent approvals, and integrates
with doom loop detection.
"""

import json
import logging
import os
import threading
from typing import Any, Callable, Dict, List, Optional

from .rules import PermissionRule, PermissionAction, PermissionResult, PersistentApproval
from .doom_loop import DoomLoopDetector

logger = logging.getLogger(__name__)

# Default storage path
DEFAULT_PERMISSIONS_DIR = os.path.expanduser("~/.praison/permissions")


class PermissionManager:
    """
    Manages permission rules and approvals.
    
    Provides pattern-based permission checking with persistent
    approval storage and doom loop detection.
    
    Example:
        manager = PermissionManager()
        
        # Add rules
        manager.add_rule(PermissionRule(
            pattern="bash:rm *",
            action=PermissionAction.ASK,
            description="Require approval for rm commands"
        ))
        
        manager.add_rule(PermissionRule(
            pattern="read:*",
            action=PermissionAction.ALLOW,
            description="Allow all read operations"
        ))
        
        # Check permission
        result = manager.check("bash:rm -rf /tmp/test")
        if result.needs_approval:
            # Ask user
            approved = ask_user(result.target)
            manager.approve(result.target, approved)
    """
    
    def __init__(
        self,
        storage_dir: Optional[str] = None,
        agent_name: Optional[str] = None,
        approval_callback: Optional[Callable[[str, str], bool]] = None,
    ):
        """
        Initialize the permission manager.
        
        Args:
            storage_dir: Directory for persistent storage
            agent_name: Optional agent name for filtering rules
            approval_callback: Optional callback for user approval
        """
        self.storage_dir = storage_dir or DEFAULT_PERMISSIONS_DIR
        self.agent_name = agent_name
        self.approval_callback = approval_callback
        
        self._rules: List[PermissionRule] = []
        self._approvals: List[PersistentApproval] = []
        self._doom_detector = DoomLoopDetector()
        self._lock = threading.RLock()
        
        # Ensure storage directory exists
        os.makedirs(self.storage_dir, exist_ok=True)
        
        # Load persistent data
        self._load_rules()
        self._load_approvals()
    
    def _get_rules_path(self) -> str:
        """Get path to rules file."""
        return os.path.join(self.storage_dir, "rules.json")
    
    def _get_approvals_path(self) -> str:
        """Get path to approvals file."""
        return os.path.join(self.storage_dir, "approvals.json")
    
    def _load_rules(self):
        """Load rules from disk."""
        path = self._get_rules_path()
        if os.path.exists(path):
            try:
                with open(path, "r") as f:
                    data = json.load(f)
                self._rules = [PermissionRule.from_dict(r) for r in data]
            except (json.JSONDecodeError, IOError) as e:
                logger.warning(f"Failed to load rules: {e}")
    
    def _save_rules(self):
        """Save rules to disk."""
        path = self._get_rules_path()
        try:
            with open(path, "w") as f:
                json.dump([r.to_dict() for r in self._rules], f, indent=2)
        except IOError as e:
            logger.error(f"Failed to save rules: {e}")
    
    def _load_approvals(self):
        """Load approvals from disk."""
        path = self._get_approvals_path()
        if os.path.exists(path):
            try:
                with open(path, "r") as f:
                    data = json.load(f)
                self._approvals = [PersistentApproval.from_dict(a) for a in data]
                # Filter out expired approvals
                self._approvals = [a for a in self._approvals if a.is_valid()]
            except (json.JSONDecodeError, IOError) as e:
                logger.warning(f"Failed to load approvals: {e}")
    
    def _save_approvals(self):
        """Save approvals to disk."""
        path = self._get_approvals_path()
        try:
            # Filter out expired and one-time approvals
            persistent = [
                a for a in self._approvals
                if a.is_valid() and a.scope in ("session", "always")
            ]
            with open(path, "w") as f:
                json.dump([a.to_dict() for a in persistent], f, indent=2)
        except IOError as e:
            logger.error(f"Failed to save approvals: {e}")
    
    def add_rule(self, rule: PermissionRule) -> str:
        """
        Add a permission rule.
        
        Args:
            rule: The rule to add
            
        Returns:
            The rule ID
        """
        with self._lock:
            self._rules.append(rule)
            # Sort by priority (higher first)
            self._rules.sort(key=lambda r: r.priority, reverse=True)
            self._save_rules()
        return rule.id
    
    def remove_rule(self, rule_id: str) -> bool:
        """
        Remove a permission rule.
        
        Args:
            rule_id: The rule ID to remove
            
        Returns:
            True if found and removed
        """
        with self._lock:
            for i, rule in enumerate(self._rules):
                if rule.id == rule_id:
                    self._rules.pop(i)
                    self._save_rules()
                    return True
        return False
    
    def get_rules(self, agent_name: Optional[str] = None) -> List[PermissionRule]:
        """
        Get all rules, optionally filtered by agent.
        
        Args:
            agent_name: Optional agent name to filter by
            
        Returns:
            List of matching rules
        """
        with self._lock:
            if agent_name is None:
                return self._rules.copy()
            return [
                r for r in self._rules
                if r.agent_name is None or r.agent_name == agent_name
            ]
    
    def check(self, target: str, agent_name: Optional[str] = None) -> PermissionResult:
        """
        Check permission for a target.
        
        Args:
            target: The target to check (e.g., "bash:rm -rf /tmp")
            agent_name: Optional agent name
            
        Returns:
            PermissionResult with the decision
        """
        agent = agent_name or self.agent_name
        
        with self._lock:
            # Check persistent approvals first
            for approval in self._approvals:
                if approval.matches(target, agent):
                    return PermissionResult(
                        action=PermissionAction.ALLOW if approval.approved else PermissionAction.DENY,
                        target=target,
                        reason=f"Persistent approval: {'approved' if approval.approved else 'denied'}",
                        approved=approval.approved,
                    )
            
            # Check rules
            for rule in self._rules:
                if rule.agent_name and agent and rule.agent_name != agent:
                    continue
                
                if rule.matches(target):
                    return PermissionResult(
                        action=rule.action,
                        rule=rule,
                        target=target,
                        reason=rule.description or f"Matched rule: {rule.pattern}",
                    )
        
        # Default: ask
        return PermissionResult(
            action=PermissionAction.ASK,
            target=target,
            reason="No matching rule, requires approval",
        )
    
    def approve(
        self,
        target: str,
        approved: bool,
        scope: str = "once",
        agent_name: Optional[str] = None,
    ) -> PersistentApproval:
        """
        Record an approval decision.
        
        Args:
            target: The target that was approved/denied
            approved: Whether it was approved
            scope: Scope of approval (once, session, always)
            agent_name: Optional agent name
            
        Returns:
            The created PersistentApproval
        """
        approval = PersistentApproval(
            pattern=target,
            approved=approved,
            scope=scope,
            agent_name=agent_name or self.agent_name,
        )
        
        with self._lock:
            self._approvals.append(approval)
            if scope in ("session", "always"):
                self._save_approvals()
        
        return approval
    
    def check_and_approve(
        self,
        target: str,
        agent_name: Optional[str] = None,
    ) -> PermissionResult:
        """
        Check permission and request approval if needed.
        
        Uses the approval_callback if set.
        
        Args:
            target: The target to check
            agent_name: Optional agent name
            
        Returns:
            PermissionResult with final decision
        """
        result = self.check(target, agent_name)
        
        if result.needs_approval and self.approval_callback:
            approved = self.approval_callback(target, result.reason)
            result.approved = approved
            self.approve(target, approved, scope="once", agent_name=agent_name)
        
        return result
    
    def check_doom_loop(
        self,
        tool_name: str,
        arguments: Optional[Dict[str, Any]] = None,
    ):
        """
        Check for doom loop and record tool call.
        
        Args:
            tool_name: Name of the tool
            arguments: Tool arguments
            
        Returns:
            DoomLoopResult
        """
        return self._doom_detector.record_and_check(tool_name, arguments)
    
    def get_doom_stats(self) -> Dict[str, Any]:
        """Get doom loop detector statistics."""
        return self._doom_detector.get_stats()
    
    def reset_doom_detector(self):
        """Reset the doom loop detector."""
        self._doom_detector.reset()
    
    def clear_approvals(self, scope: Optional[str] = None):
        """
        Clear approvals.
        
        Args:
            scope: Optional scope to clear (None = all)
        """
        with self._lock:
            if scope is None:
                self._approvals.clear()
            else:
                self._approvals = [a for a in self._approvals if a.scope != scope]
            self._save_approvals()
    
    def clear_rules(self):
        """Clear all rules."""
        with self._lock:
            self._rules.clear()
            self._save_rules()
    
    def set_approval_callback(self, callback: Callable[[str, str], bool]):
        """Set the approval callback."""
        self.approval_callback = callback
    
    def to_dict(self) -> Dict[str, Any]:
        """Export manager state to dictionary."""
        with self._lock:
            return {
                "rules": [r.to_dict() for r in self._rules],
                "approvals": [a.to_dict() for a in self._approvals],
                "agent_name": self.agent_name,
            }
    
    def from_dict(self, data: Dict[str, Any]):
        """Import manager state from dictionary."""
        with self._lock:
            self._rules = [PermissionRule.from_dict(r) for r in data.get("rules", [])]
            self._approvals = [PersistentApproval.from_dict(a) for a in data.get("approvals", [])]
            if "agent_name" in data:
                self.agent_name = data["agent_name"]
