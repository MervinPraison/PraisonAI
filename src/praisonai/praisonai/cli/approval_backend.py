"""
Interactive CLI approval backend for PraisonAI.

Provides interactive prompts for tool approval with persistent rules.
"""

import asyncio
import os
from typing import Optional, Dict, Any

from praisonaiagents.approval import ApprovalRequest, ApprovalDecision
from praisonaiagents.permissions import (
    PermissionManager,
    PermissionRule,
    PermissionAction,
    PermissionMode,
)


class InteractiveCLIApprovalBackend:
    """
    Interactive CLI backend for tool approvals.
    
    Provides terminal prompts with options to:
    - Allow once
    - Always allow (persist as rule)
    - Deny
    
    Integrates with PermissionManager for persistent project-scoped rules.
    """
    
    def __init__(
        self,
        project_dir: Optional[str] = None,
        permission_mode: PermissionMode = PermissionMode.DEFAULT,
        non_interactive: bool = False,
        permissions_config: Optional[Dict[str, Any]] = None,
    ):
        """
        Initialize the interactive CLI approval backend.
        
        Args:
            project_dir: Project directory for scoped permissions
            permission_mode: Permission mode (default, accept_edits, dont_ask, bypass, plan)
            non_interactive: Whether to auto-approve/deny without prompting
            permissions_config: Declarative permission rules from YAML/CLI/Python
        """
        self.project_dir = project_dir or os.getcwd()
        self.permission_mode = permission_mode
        self.non_interactive = non_interactive
        
        # Initialize permission manager with project-scoped storage
        permissions_dir = os.path.join(self.project_dir, ".praisonai", "permissions")
        self.permission_manager = PermissionManager(storage_dir=permissions_dir)
        
        # Load declarative permissions if provided
        if permissions_config:
            self.permission_manager.load_rules_from_config(permissions_config, priority_base=75)
    
    def _build_target_string(self, request: ApprovalRequest) -> str:
        """Build target string for permission check."""
        if "command" in request.arguments:
            return f"{request.tool_name}:{request.arguments['command']}"
        elif request.arguments:
            # Include first arg value for more specific matching
            first_arg = next(iter(request.arguments.values()), "") if request.arguments else ""
            if isinstance(first_arg, str) and len(first_arg) < 100:
                return f"{request.tool_name}:{first_arg}"
            else:
                return f"{request.tool_name}:"
        else:
            return f"{request.tool_name}:"
    
    def _format_tool_call(self, request: ApprovalRequest) -> str:
        """Format a tool call for display."""
        tool_name = request.tool_name
        args = request.arguments
        
        # Format arguments nicely
        if args:
            arg_strs = []
            for key, value in args.items():
                if isinstance(value, str) and len(value) > 50:
                    value = value[:47] + "..."
                arg_strs.append(f"{key}={repr(value)}")
            args_display = ", ".join(arg_strs)
        else:
            args_display = ""
        
        return f"{tool_name}({args_display})"
    
    def _prompt_user(self, request: ApprovalRequest) -> tuple[bool, bool]:
        """
        Prompt user for approval decision.
        
        Returns:
            Tuple of (approved, persist_as_always)
        """
        if self.non_interactive:
            # In non-interactive mode, check declared rules before defaulting to deny
            # This allows CI-safe operation with declarative permissions
            target = self._build_target_string(request)
            result = self.permission_manager.check(target, agent_name=request.agent_name)
            
            if result.action == PermissionAction.ALLOW:
                return (True, False)
            elif result.action == PermissionAction.DENY:
                return (False, False)
            else:  # ASK - in non-interactive, default to deny
                return (False, False)
        
        # Interactive prompt
        tool_display = self._format_tool_call(request)
        risk_color = {
            "critical": "\033[91m",  # Red
            "high": "\033[93m",      # Yellow
            "medium": "\033[96m",    # Cyan
            "low": "\033[92m",       # Green
        }.get(request.risk_level, "\033[0m")
        
        print(f"\n{risk_color}⚠ Tool Approval Required{chr(27)}[0m")
        print(f"Tool: {tool_display}")
        print(f"Risk: {request.risk_level}")
        if request.agent_name:
            print(f"Agent: {request.agent_name}")
        
        print("\nOptions:")
        print("  [a] Allow once")
        print("  [A] Always allow (persist rule)")
        print("  [d] Deny")
        print("  [D] Always deny (persist rule)")
        
        while True:
            try:
                choice = input("\nYour choice: ").strip()
                
                if choice == "a":
                    return (True, False)
                elif choice == "A":
                    return (True, True)
                elif choice == "d":
                    return (False, False)
                elif choice == "D":
                    return (False, True)
                else:
                    print("Invalid choice. Please enter a, A, d, or D.")
            except (EOFError, KeyboardInterrupt):
                print("\n\nApproval cancelled.")
                return (False, False)
    
    def _create_pattern(self, request: ApprovalRequest) -> str:
        """Create a permission pattern from the request."""
        # Create a pattern that matches this specific tool
        # Can be made more sophisticated to support wildcards
        tool_name = request.tool_name
        
        # For certain tools, we can create broader patterns
        if tool_name == "bash" and "command" in request.arguments:
            cmd = request.arguments["command"]
            # Extract first word as command type
            cmd_parts = cmd.split()
            if cmd_parts:
                first_word = cmd_parts[0]
                # For git commands, create pattern for all git commands
                if first_word == "git":
                    return f"{tool_name}:git *"
                # For safe commands, broader patterns
                elif first_word in ["ls", "pwd", "echo", "cat", "grep"]:
                    return f"{tool_name}:{first_word} *"
        
        # Default to exact tool name
        return f"{tool_name}:*"
    
    def _decision_from_mode(self, request: ApprovalRequest) -> Optional[ApprovalDecision]:
        """
        Check if permission mode provides an immediate decision.
        
        Returns None if mode doesn't apply, otherwise returns the decision.
        """
        # BYPASS mode: unconditional allow
        if self.permission_mode == PermissionMode.BYPASS:
            return ApprovalDecision(
                approved=True,
                reason="Bypassed by permission mode",
                approver="permission_mode"
            )
        
        # PLAN mode: unconditional deny for write/edit/shell operations
        if self.permission_mode == PermissionMode.PLAN:
            if request.tool_name in ["write", "edit", "delete", "bash", "shell"]:
                return ApprovalDecision(
                    approved=False,
                    reason="Blocked by plan mode",
                    approver="permission_mode"
                )
        
        # ACCEPT_EDITS mode: unconditional allow for edit/write operations
        if self.permission_mode == PermissionMode.ACCEPT_EDITS:
            if "edit" in request.tool_name.lower() or "write" in request.tool_name.lower():
                return ApprovalDecision(
                    approved=True,
                    reason="Auto-approved edit by permission mode",
                    approver="permission_mode"
                )
        
        # DONT_ASK mode in non-interactive: deny all asks
        if self.permission_mode == PermissionMode.DONT_ASK and self.non_interactive:
            return ApprovalDecision(
                approved=False,
                reason="Denied by don't-ask mode",
                approver="permission_mode"
            )
        
        return None
    
    async def request_approval(self, request: ApprovalRequest) -> ApprovalDecision:
        """
        Request approval for a tool execution.
        
        First checks permission modes, then existing rules, then prompts if needed.
        """
        # Check permission mode first (takes precedence)
        mode_decision = self._decision_from_mode(request)
        if mode_decision is not None:
            return mode_decision
        
        # Build target string for permission check
        target = self._build_target_string(request)
        
        # Check existing permissions
        result = self.permission_manager.check(target, agent_name=request.agent_name)
        
        if result.action == PermissionAction.ALLOW:
            return ApprovalDecision(
                approved=True,
                reason="Allowed by rule",
                approver="permission_rule",
                metadata={"rule_id": result.rule.id if result.rule else None}
            )
        elif result.action == PermissionAction.DENY:
            return ApprovalDecision(
                approved=False,
                reason="Denied by rule",
                approver="permission_rule",
                metadata={"rule_id": result.rule.id if result.rule else None}
            )
        
        # Need to ask - run prompt in thread to avoid blocking
        loop = asyncio.get_running_loop()
        approved, persist = await loop.run_in_executor(
            None, self._prompt_user, request
        )
        
        # If user wants to persist the decision
        if persist:
            pattern = self._create_pattern(request)
            action = PermissionAction.ALLOW if approved else PermissionAction.DENY
            
            # Create and add the rule
            rule = PermissionRule(
                pattern=pattern,
                action=action,
                description=f"User {'allowed' if approved else 'denied'} {request.tool_name}",
                agent_name=request.agent_name,
                priority=100,  # User rules have high priority
            )
            self.permission_manager.add_rule(rule)
        
        return ApprovalDecision(
            approved=approved,
            reason="User decision" + (" (persisted)" if persist else ""),
            approver="user",
            metadata={"persistent": persist}
        )
    
    def set_permission_mode(self, mode: PermissionMode):
        """Update the permission mode."""
        self.permission_mode = mode
    
    def get_permission_manager(self) -> PermissionManager:
        """Get the underlying permission manager for direct access."""
        return self.permission_manager