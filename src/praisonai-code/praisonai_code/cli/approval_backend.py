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
            first_arg = next(iter(request.arguments.values()), "")
            if isinstance(first_arg, str) and len(first_arg) < 100:
                return f"{request.tool_name}:{first_arg}"
        # Use wildcard for consistency with permission patterns
        return f"{request.tool_name}:*"
    
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
    
    def _prompt_user(self, request: ApprovalRequest) -> tuple[bool, bool, str, Optional[str]]:
        """
        Prompt user for approval decision.

        Returns:
            Tuple of ``(approved, persist_as_always, scope, deny_reason)`` where
            ``scope`` is ``"command"`` (narrow, command-prefix) or ``"tool"``
            (explicit blanket ``tool:*``) and ``deny_reason`` is optional
            steering feedback captured on denial (``None`` when absent).
        """
        if self.non_interactive:
            # In non-interactive mode, we're only here if the check returned ASK
            # (ALLOW/DENY are handled in request_approval), so default to deny
            return (False, False, "command", None)
        
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

        # Show a preview of the actual change for file-mutating tools so the
        # user approves the concrete change, not just a tool name.
        preview = self._render_preview(request)
        if preview:
            print(preview)

        # Compute the narrow pattern once so the user can see exactly what a
        # persisted "always" will grant.
        narrow_pattern = self._create_pattern(request, scope="command")

        print("\nOptions:")
        print("  [a] Allow once")
        print(f"  [A] Always allow this command ({narrow_pattern})")
        print(f"  [T] Always allow ALL uses of {request.tool_name} ({request.tool_name}:*)")
        print("  [d] Deny")
        print("  [D] Always deny (persist rule)")
        
        while True:
            try:
                choice = input("\nYour choice: ").strip()
                
                if choice == "a":
                    return (True, False, "command", None)
                elif choice == "A":
                    return (True, True, "command", None)
                elif choice == "T":
                    return (True, True, "tool", None)
                elif choice == "d":
                    return (False, False, "command", self._prompt_deny_reason())
                elif choice == "D":
                    return (False, True, "command", self._prompt_deny_reason())
                else:
                    print("Invalid choice. Please enter a, A, T, d, or D.")
            except (EOFError, KeyboardInterrupt):
                print("\n\nApproval cancelled.")
                return (False, False, "command", None)

    def _prompt_deny_reason(self) -> Optional[str]:
        """Optionally capture a denial reason to steer the agent.

        Returns the trimmed reason string, or ``None`` if the user provides no
        feedback (blank input) or input is unavailable.
        """
        try:
            reason = input("Reason for denial (optional, steers the agent): ").strip()
        except (EOFError, KeyboardInterrupt):
            return None
        return reason or None

    def _render_preview(self, request: ApprovalRequest) -> Optional[str]:
        """Render a change preview for file-mutating tools.

        For ``edit``/``apply_patch`` a unified diff is shown when available;
        for ``write`` the content (truncated) is shown. Returns ``None`` when
        there is nothing meaningful to preview.
        """
        tool_name = request.tool_name
        args = request.arguments or {}
        if tool_name not in ("edit", "write", "apply_patch"):
            return None

        # Prefer an already-computed diff if the caller supplied one.
        diff = args.get("diff") or args.get("patch")
        if isinstance(diff, str) and diff.strip():
            return f"\nPreview (diff):\n{diff}"

        if tool_name == "write":
            content = args.get("content") or args.get("text")
            path = args.get("path") or args.get("file_path") or ""
            if isinstance(content, str):
                shown = content if len(content) <= 2000 else content[:2000] + "\n... (truncated)"
                header = f" to {path}" if path else ""
                return f"\nPreview (content{header}):\n{shown}"

        return None
    
    def _create_pattern(self, request: ApprovalRequest, scope: str = "command") -> str:
        """Create a permission pattern from the request.

        Derives the *narrowest reasonable* persisted pattern so that approving a
        single command does not silently grant unrestricted use of a tool.

        Args:
            request: The approval request.
            scope: ``"command"`` (default) derives a command-prefix scope for
                shell tools (e.g. ``bash:git status *``) and a per-argument
                scope for other tools. ``"tool"`` is the explicit, clearly
                labelled "allow all uses of this tool" choice which emits the
                blanket ``tool_name:*`` pattern.

        Returns:
            A permission glob pattern. Malformed/unknown shell commands fall
            back to the literal target (single-use in practice) rather than a
            broad ``tool:*`` grant, preserving a fail-closed posture.
        """
        tool_name = request.tool_name

        # Explicit, clearly-labelled "always allow all uses of this tool" only.
        if scope == "tool":
            return f"{tool_name}:*"

        # Shell tools: derive a reusable command-prefix scope via the shared
        # core helper so declarative (YAML/--allow) and interactive rules scope
        # identically. Unknown/compound commands stay literal (fail-closed).
        if tool_name in ("bash", "shell") and "command" in request.arguments:
            command = request.arguments["command"]
            if isinstance(command, str) and command.strip():
                from praisonaiagents.permissions import derive_pattern

                return derive_pattern(f"{tool_name}:{command}")
            return f"{tool_name}:*"

        # Non-shell tools: scope to the first argument value when it is a short
        # string, otherwise fall back to the tool name. This never over-grants
        # beyond the specific target the user actually approved.
        if request.arguments:
            first_arg = next(iter(request.arguments.values()), "")
            if isinstance(first_arg, str) and first_arg and len(first_arg) < 100:
                return f"{tool_name}:{first_arg}"

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
        approved, persist, scope, deny_reason = await loop.run_in_executor(
            None, self._prompt_user, request
        )
        
        # If user wants to persist the decision
        if persist:
            pattern = self._create_pattern(request, scope=scope)
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

        # Surface any denial feedback so the agent can steer instead of just
        # aborting. A denied approval with a reason becomes a correction.
        metadata: Dict[str, Any] = {"persistent": persist}
        if not approved and deny_reason:
            metadata["feedback"] = deny_reason

        reason_text = "User decision" + (" (persisted)" if persist else "")
        if not approved and deny_reason:
            reason_text = f"User denied: {deny_reason}"

        return ApprovalDecision(
            approved=approved,
            reason=reason_text,
            approver="user",
            metadata=metadata,
        )
    
    def set_permission_mode(self, mode: PermissionMode):
        """Update the permission mode."""
        self.permission_mode = mode
    
    def get_permission_manager(self) -> PermissionManager:
        """Get the underlying permission manager for direct access."""
        return self.permission_manager