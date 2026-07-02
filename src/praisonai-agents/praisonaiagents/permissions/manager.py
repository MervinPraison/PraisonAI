"""
Permission Manager for PraisonAI Agents.

Manages permission rules, persistent approvals, and integrates
with doom loop detection.
"""

import json
import logging
from praisonaiagents._logging import get_logger
import os
import threading
from typing import Any, Callable, Dict, List, Optional

from .rules import PermissionRule, PermissionAction, PermissionResult, PersistentApproval
from .doom_loop import DoomLoopDetector

from ..paths import get_permissions_dir

logger = get_logger(__name__)

# Default storage path (uses centralized paths - DRY)
DEFAULT_PERMISSIONS_DIR = str(get_permissions_dir())

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
        workspace_root: Optional[str] = None,
    ):
        """
        Initialize the permission manager.
        
        Args:
            storage_dir: Directory for persistent storage
            agent_name: Optional agent name for filtering rules
            approval_callback: Optional callback for user approval
            workspace_root: Optional project/workspace root. When set, shell
                and file targets that resolve *outside* this root emit a
                distinct ``external_dir:<parent>/*`` sub-target (default
                ``ask``), gating out-of-workspace access with an extra
                approval. When ``None`` (default) no boundary check runs and
                behaviour is unchanged.
        """
        self.storage_dir = storage_dir or DEFAULT_PERMISSIONS_DIR
        self.agent_name = agent_name
        self.approval_callback = approval_callback
        self.workspace_root = (
            os.path.realpath(workspace_root) if workspace_root else None
        )
        
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
    
    def save_rules(self):
        """Public method to save rules to disk."""
        with self._lock:
            self._save_rules()
    
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
    
    # Prefixes that should be decomposed into command-structure-aware
    # sub-targets before matching (command-aware permission matching).
    _SHELL_PREFIXES = ("bash:", "shell:")

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

        # Command-aware matching: shell targets are decomposed into their
        # constituent operations so deny rules fire regardless of where the
        # operation appears in a compound command (&&, ;, |, $(), redirects).
        prefix = next(
            (p for p in self._SHELL_PREFIXES if target.startswith(p)), None
        )
        if prefix is not None:
            command = target[len(prefix):]
            structured = self._check_shell_command(prefix, command, agent)
            if structured is not None:
                return structured

        return self._check_flat(target, agent)

    def _check_flat(self, target: str, agent: Optional[str]) -> PermissionResult:
        """Legacy flat matching against approvals and rules for a target."""
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

    def _check_shell_command(
        self, prefix: str, command: str, agent: Optional[str]
    ) -> Optional[PermissionResult]:
        """Command-structure-aware check for a shell command target.

        Decomposes the command into its constituent operations and evaluates
        each as its own sub-target. Aggregates with deny-wins, then ask,
        then allow semantics. Returns ``None`` to defer to flat matching when
        decomposition yields a single operation identical to the original
        target (no compound structure), preserving legacy behaviour exactly.
        """
        original_target = prefix + command
        try:
            from .command_parser import parse_command
            ops = parse_command(command)
        except Exception:
            return None

        # Build the list of sub-targets to evaluate.
        sub_targets: List[str] = []
        for op in ops:
            cmd_str = op.command_string
            if cmd_str:
                sub_targets.append(prefix + cmd_str)
            for path in op.write_targets:
                sub_targets.append(f"write:{path}")
            # Workspace-boundary gate: any write target or path-like arg that
            # resolves outside the workspace root gets a distinct
            # ``external_dir:`` sub-target (default ``ask``).
            if self.workspace_root is not None:
                boundary_paths = list(op.write_targets) + op.path_args
                # An executable referenced by path (``/tmp/tool``, ``../tool``)
                # runs code outside the workspace; a bare name (``rm``) is
                # PATH-resolved and must not trigger a boundary prompt.
                if op.executable and (
                    op.executable.startswith(("/", "~", "./", "../", "$"))
                    or "/" in op.executable
                ):
                    boundary_paths.append(op.executable)
                for path in boundary_paths:
                    ext = self._external_dir_target(path)
                    if ext is not None:
                        sub_targets.append(ext)

        # No structured decomposition possible, or it collapses to exactly the
        # original target — defer to the existing flat matcher.
        if not sub_targets or sub_targets == [original_target]:
            return None

        results = [(t, self._check_flat(t, agent)) for t in sub_targets]

        # Also fold in an explicit match on the *original* compound target so a
        # legacy flat rule/approval (e.g. ``deny: bash:cd /tmp && rm *``) still
        # participates. The default "No matching rule" ASK is intentionally
        # excluded so it does not override allowed sub-operations.
        original_res = self._check_flat(original_target, agent)
        if (original_res.rule is not None) or original_res.approved is not None:
            results.append((original_target, original_res))

        # Deny wins.
        for sub_target, res in results:
            if res.action == PermissionAction.DENY:
                res.reason = (
                    f"Denied sub-operation '{sub_target}' ({res.reason})"
                )
                res.target = original_target
                return res

        # Then ask: if any sub-operation requires approval.
        for sub_target, res in results:
            if res.action == PermissionAction.ASK:
                res.reason = (
                    f"Sub-operation '{sub_target}' requires approval "
                    f"({res.reason})"
                )
                res.target = original_target
                return res

        # All allowed.
        return PermissionResult(
            action=PermissionAction.ALLOW,
            target=original_target,
            reason="All shell sub-operations allowed",
        )

    def _external_dir_target(self, path: str) -> Optional[str]:
        """Return an ``external_dir:<parent>/*`` target if *path* escapes root.

        Resolves *path* (``~``, ``$VARS``, ``..``) against ``workspace_root``
        using the shared ``path_safety`` containment logic. In-workspace paths
        return ``None`` so existing flows are unaffected.
        """
        if self.workspace_root is None:
            return None
        # Fail *closed*: if the boundary check cannot be performed (import or
        # resolution failure), gate the raw path behind ``external_dir:`` rather
        # than silently allowing it. A deny rule still wins over this ask.
        fail_closed = f"external_dir:{path}/*"
        try:
            from ..tools.path_safety import resolve_within_root, resolve_path
        except Exception as e:  # noqa: BLE001
            logger.error(
                "Workspace boundary check unavailable for path '%s' "
                "(agent=%s): %s. Requiring approval instead of allowing.",
                path, self.agent_name, e,
            )
            return fail_closed
        try:
            if resolve_within_root(path, self.workspace_root) is not None:
                return None
            resolved = resolve_path(path, self.workspace_root)
            parent = os.path.dirname(resolved) or resolved
            return f"external_dir:{parent}/*"
        except Exception as e:  # noqa: BLE001
            logger.warning(
                "Could not resolve path '%s' for workspace boundary check "
                "(agent=%s): %s. Requiring approval.",
                path, self.agent_name, e,
            )
            return fail_closed

    def check_path_boundary(
        self, path: str, agent_name: Optional[str] = None
    ) -> Optional[PermissionResult]:
        """Check a single file-tool target against the workspace boundary.

        Shared boundary policy for file tools (``write_file``/``edit``/
        ``apply_patch``). Returns ``None`` when no ``workspace_root`` is
        configured or the path is inside it (i.e. no extra gate); otherwise
        returns the ``external_dir:`` permission decision (default ``ask``).
        """
        ext = self._external_dir_target(path)
        if ext is None:
            return None
        return self.check(ext, agent_name)

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
    
    def load_rules_from_config(self, permissions_config: Dict[str, Any], priority_base: int = 50, persist: bool = False):
        """
        Load permission rules from configuration (YAML/CLI/Python).
        
        Args:
            permissions_config: Dictionary mapping patterns to actions or detailed configs
                               e.g., {"read:*": "allow", "bash:rm *": {"action": "deny", "description": "..."}}
            priority_base: Base priority for these rules (default: 50, between default and user rules)
            persist: Whether to persist these rules to disk (default: False for ephemeral CI/YAML rules)
        """
        if not permissions_config:
            return
        
        with self._lock:
            incoming_rules = []
            
            for pattern, config in permissions_config.items():
                try:
                    if isinstance(config, str):
                        # Simple format: pattern -> action
                        rule = PermissionRule.from_config(pattern, config, priority=priority_base)
                    elif isinstance(config, dict):
                        # Detailed format: pattern -> {action, description, ...}
                        action = config.get("action", "ask")
                        rule = PermissionRule.from_config(
                            pattern,
                            action,
                            description=config.get("description"),
                            is_regex=config.get("is_regex", False),
                            priority=config.get("priority", priority_base),
                            agent_name=config.get("agent_name"),
                            enabled=config.get("enabled", True),
                        )
                    else:
                        logger.warning(
                            "Invalid permission config for pattern '%s': %r. "
                            "Use 'allow|deny|ask' or {action, description, is_regex, priority, agent_name, enabled}.",
                            pattern,
                            config,
                        )
                        continue
                except (TypeError, ValueError) as e:
                    logger.warning(
                        "Skipping invalid permission rule for pattern '%s': %s. "
                        "Valid actions are: allow, deny, ask.",
                        pattern,
                        e,
                    )
                    continue
                    
                incoming_rules.append(rule)
            
            # Remove existing rules with same pattern to avoid duplicates
            # (pattern, agent_name, is_regex) uniquely identifies a rule for matching
            incoming_keys = {(r.pattern, r.agent_name, r.is_regex) for r in incoming_rules}
            self._rules = [
                r for r in self._rules
                if (r.pattern, r.agent_name, r.is_regex) not in incoming_keys
            ]
            self._rules.extend(incoming_rules)
            
            # Re-sort by priority
            self._rules.sort(key=lambda r: r.priority, reverse=True)
            
            # Only persist if explicitly requested (not for ephemeral CI/YAML rules)
            if persist:
                self._save_rules()
