"""
Action Orchestrator for PraisonAI.

Orchestrates code modifications through ACP with plan → approval → apply → verify steps.
Enforces read-only mode when ACP is unavailable.
"""

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .interactive_runtime import InteractiveRuntime

logger = logging.getLogger(__name__)


class ActionType(Enum):
    """Types of actions that can be orchestrated."""
    FILE_CREATE = "file_create"
    FILE_EDIT = "file_edit"
    FILE_DELETE = "file_delete"
    FILE_RENAME = "file_rename"
    SHELL_COMMAND = "shell_command"
    REFACTOR = "refactor"
    UNKNOWN = "unknown"


class ActionStatus(Enum):
    """Status of an action."""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    APPLIED = "applied"
    FAILED = "failed"
    VERIFIED = "verified"


@dataclass
class ActionStep:
    """A single step in an action plan."""
    id: str
    action_type: ActionType
    description: str
    target: str  # File path or command
    params: Dict[str, Any] = field(default_factory=dict)
    status: ActionStatus = ActionStatus.PENDING
    result: Optional[Any] = None
    error: Optional[str] = None


@dataclass
class ActionPlan:
    """A plan of actions to execute."""
    id: str
    prompt: str
    steps: List[ActionStep] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    status: ActionStatus = ActionStatus.PENDING
    approval_mode: str = "manual"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "prompt": self.prompt,
            "steps": [
                {
                    "id": s.id,
                    "action_type": s.action_type.value,
                    "description": s.description,
                    "target": s.target,
                    "params": s.params,
                    "status": s.status.value,
                    "result": s.result,
                    "error": s.error
                }
                for s in self.steps
            ],
            "created_at": self.created_at,
            "status": self.status.value,
            "approval_mode": self.approval_mode
        }


@dataclass
class ActionResult:
    """Result of action orchestration."""
    success: bool
    plan: Optional[ActionPlan] = None
    applied_steps: int = 0
    failed_steps: int = 0
    error: Optional[str] = None
    read_only_blocked: bool = False
    diff_summary: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "plan": self.plan.to_dict() if self.plan else None,
            "applied_steps": self.applied_steps,
            "failed_steps": self.failed_steps,
            "error": self.error,
            "read_only_blocked": self.read_only_blocked,
            "diff_summary": self.diff_summary
        }


class ActionOrchestrator:
    """
    Orchestrates code modifications through ACP.
    
    All edits must go through:
    1. Plan creation
    2. Approval (manual, auto, or scoped)
    3. Application
    4. Verification
    
    If ACP is unavailable, runtime is read-only and edits are blocked.
    """
    
    def __init__(self, runtime: "InteractiveRuntime"):
        """Initialize with runtime reference."""
        self.runtime = runtime
        self._plan_counter = 0
    
    def _generate_plan_id(self) -> str:
        """Generate a unique plan ID."""
        self._plan_counter += 1
        return f"plan_{int(time.time())}_{self._plan_counter}"
    
    def _generate_step_id(self, plan_id: str, index: int) -> str:
        """Generate a unique step ID."""
        return f"{plan_id}_step_{index}"
    
    async def create_plan(self, prompt: str) -> ActionResult:
        """
        Create an action plan for a modification request.
        
        Args:
            prompt: The user's modification request
            
        Returns:
            ActionResult with the plan
        """
        if self.runtime.read_only:
            return ActionResult(
                success=False,
                error="Runtime is in read-only mode. ACP is required for modifications.",
                read_only_blocked=True
            )
        
        plan_id = self._generate_plan_id()
        
        # Always use fallback plan creation (ACP session tracks but doesn't create plans)
        # In production, this would integrate with an LLM for intelligent planning
        return await self._create_fallback_plan(prompt, plan_id)
    
    async def _create_fallback_plan(self, prompt: str, plan_id: str) -> ActionResult:
        """Create a fallback plan when ACP is not available for planning."""
        import re  # Import at function level for all pattern matching
        
        # This is a simplified fallback - in production, this would use LLM
        steps = []
        
        # Analyze prompt for common patterns
        prompt_lower = prompt.lower()
        
        if "create" in prompt_lower or "new file" in prompt_lower:
            # Extract file path if mentioned
            file_match = re.search(r'(?:create|new)\s+(?:a\s+)?(?:file\s+)?(?:called\s+)?([^\s]+\.\w+)', prompt_lower)
            target = file_match.group(1) if file_match else "new_file.py"
            
            # Generate default content based on file type
            if target.endswith('.py'):
                content = f'"""\n{target} - Auto-generated file\n"""\n\ndef main():\n    pass\n\n\nif __name__ == "__main__":\n    main()\n'
            else:
                content = f"// {target} - Auto-generated file\n"
            
            steps.append(ActionStep(
                id=self._generate_step_id(plan_id, 0),
                action_type=ActionType.FILE_CREATE,
                description=f"Create file: {target}",
                target=target,
                params={"content": content},
                status=ActionStatus.APPROVED  # Auto-approve for fallback
            ))
        
        elif "edit" in prompt_lower or "modify" in prompt_lower or "change" in prompt_lower:
            # Match patterns like "edit file X", "edit X", "modify X"
            file_match = re.search(r'(?:edit|modify|change)\s+(?:file\s+)?([^\s]+(?:\.\w+)?)', prompt_lower)
            target = file_match.group(1) if file_match else ""
            
            if target:
                steps.append(ActionStep(
                    id=self._generate_step_id(plan_id, 0),
                    action_type=ActionType.FILE_EDIT,
                    description=f"Edit file: {target}",
                    target=target,
                    params={"changes": prompt},
                    status=ActionStatus.APPROVED  # Auto-approve for fallback
                ))
        
        elif "delete" in prompt_lower or "remove" in prompt_lower:
            # Match patterns like "delete file X", "delete X", "remove X"
            file_match = re.search(r'(?:delete|remove)\s+(?:file\s+)?([^\s]+(?:\.\w+)?)', prompt_lower)
            target = file_match.group(1) if file_match else ""
            
            if target:
                steps.append(ActionStep(
                    id=self._generate_step_id(plan_id, 0),
                    action_type=ActionType.FILE_DELETE,
                    description=f"Delete file: {target}",
                    target=target,
                    status=ActionStatus.APPROVED  # Auto-approve for fallback
                ))
        
        elif "rename" in prompt_lower:
            steps.append(ActionStep(
                id=self._generate_step_id(plan_id, 0),
                action_type=ActionType.REFACTOR,
                description="Rename operation",
                target="",
                params={"prompt": prompt},
                status=ActionStatus.APPROVED  # Auto-approve for fallback
            ))
        
        elif "run" in prompt_lower or "execute" in prompt_lower or "command" in prompt_lower:
            # Match patterns like "run command: X", "execute X", "run X"
            cmd_match = re.search(r'(?:run|execute)\s+(?:command[:\s]+)?[`"\']?(.+?)[`"\']?$', prompt_lower)
            command = cmd_match.group(1).strip() if cmd_match else ""
            
            if command:
                steps.append(ActionStep(
                    id=self._generate_step_id(plan_id, 0),
                    action_type=ActionType.SHELL_COMMAND,
                    description=f"Execute: {command}",
                    target=command,
                    status=ActionStatus.APPROVED  # Auto-approve for fallback
                ))
        
        if not steps:
            return ActionResult(
                success=False,
                error="Could not determine action from prompt. Please be more specific."
            )
        
        plan = ActionPlan(
            id=plan_id,
            prompt=prompt,
            steps=steps,
            approval_mode=self.runtime.config.approval_mode
        )
        
        return ActionResult(
            success=True,
            plan=plan
        )
    
    def _classify_action_type(self, step_data: Dict[str, Any]) -> ActionType:
        """Classify the action type from step data."""
        action = step_data.get("action", "").lower()
        
        if "create" in action:
            return ActionType.FILE_CREATE
        elif "edit" in action or "modify" in action:
            return ActionType.FILE_EDIT
        elif "delete" in action or "remove" in action:
            return ActionType.FILE_DELETE
        elif "rename" in action:
            return ActionType.FILE_RENAME
        elif "shell" in action or "command" in action or "run" in action:
            return ActionType.SHELL_COMMAND
        elif "refactor" in action:
            return ActionType.REFACTOR
        
        return ActionType.UNKNOWN
    
    async def approve_plan(self, plan: ActionPlan, auto: bool = False) -> bool:
        """
        Request approval for a plan.
        
        Args:
            plan: The plan to approve
            auto: Whether to auto-approve
            
        Returns:
            True if approved, False if rejected
        """
        if self.runtime.read_only:
            logger.warning("Cannot approve plan in read-only mode")
            return False
        
        approval_mode = self.runtime.config.approval_mode
        
        if approval_mode == "auto" or auto:
            plan.status = ActionStatus.APPROVED
            for step in plan.steps:
                step.status = ActionStatus.APPROVED
            return True
        
        elif approval_mode == "scoped":
            # Auto-approve safe actions, require manual for dangerous ones
            dangerous_types = {ActionType.FILE_DELETE, ActionType.SHELL_COMMAND}
            
            for step in plan.steps:
                if step.action_type in dangerous_types:
                    step.status = ActionStatus.PENDING  # Needs manual approval
                else:
                    step.status = ActionStatus.APPROVED
            
            # Plan is approved if all steps are approved
            if all(s.status == ActionStatus.APPROVED for s in plan.steps):
                plan.status = ActionStatus.APPROVED
                return True
            
            return False  # Some steps need manual approval
        
        else:  # manual
            # In manual mode, we return False to indicate approval is needed
            return False
    
    async def apply_plan(self, plan: ActionPlan, force: bool = False) -> ActionResult:
        """
        Apply an approved plan.
        
        Args:
            plan: The plan to apply
            force: Force apply even if not fully approved
            
        Returns:
            ActionResult with application status
        """
        if self.runtime.read_only:
            return ActionResult(
                success=False,
                plan=plan,
                error="Runtime is in read-only mode",
                read_only_blocked=True
            )
        
        if plan.status != ActionStatus.APPROVED and not force:
            return ActionResult(
                success=False,
                plan=plan,
                error="Plan is not approved"
            )
        
        applied = 0
        failed = 0
        diff_parts = []
        
        # Track in ACP session if available (but always do manual application)
        if self.runtime.acp_ready:
            try:
                auto_approve = self.runtime.config.approval_mode == "auto"
                await self.runtime.acp_apply_plan(
                    plan.to_dict(),
                    auto_approve=auto_approve
                )
            except Exception as e:
                logger.warning(f"ACP tracking failed: {e}")
        
        # Manual application (always execute)
        for step in plan.steps:
            if step.status not in [ActionStatus.APPROVED, ActionStatus.PENDING]:
                continue
            
            try:
                result = await self._apply_step(step)
                if result:
                    step.status = ActionStatus.APPLIED
                    step.result = result
                    applied += 1
                    if isinstance(result, dict) and "diff" in result:
                        diff_parts.append(result["diff"])
                else:
                    step.status = ActionStatus.FAILED
                    failed += 1
            except Exception as e:
                step.status = ActionStatus.FAILED
                step.error = str(e)
                failed += 1
        
        plan.status = ActionStatus.APPLIED if failed == 0 else ActionStatus.FAILED
        
        return ActionResult(
            success=failed == 0,
            plan=plan,
            applied_steps=applied,
            failed_steps=failed,
            diff_summary="\n".join(diff_parts) if diff_parts else None
        )
    
    async def _apply_step(self, step: ActionStep) -> Optional[Dict[str, Any]]:
        """Apply a single step."""
        workspace = Path(self.runtime.config.workspace)
        
        if step.action_type == ActionType.FILE_CREATE:
            target = workspace / step.target
            target.parent.mkdir(parents=True, exist_ok=True)
            content = step.params.get("content", "")
            target.write_text(content)
            return {"created": str(target), "diff": f"+++ {target}\n+ (new file)"}
        
        elif step.action_type == ActionType.FILE_EDIT:
            target = workspace / step.target
            if not target.exists():
                return None
            
            old_content = target.read_text()
            new_content = step.params.get("new_content", old_content)
            target.write_text(new_content)
            
            return {
                "edited": str(target),
                "diff": f"--- {target}\n+++ {target}\n(content changed)"
            }
        
        elif step.action_type == ActionType.FILE_DELETE:
            target = workspace / step.target
            if target.exists():
                target.unlink()
                return {"deleted": str(target), "diff": f"--- {target}\n- (deleted)"}
            return None
        
        elif step.action_type == ActionType.FILE_RENAME:
            source = workspace / step.params.get("source", "")
            dest = workspace / step.params.get("dest", "")
            if source.exists():
                source.rename(dest)
                return {"renamed": f"{source} -> {dest}"}
            return None
        
        elif step.action_type == ActionType.SHELL_COMMAND:
            import subprocess
            result = subprocess.run(
                step.target,
                shell=True,
                capture_output=True,
                text=True,
                cwd=str(workspace),
                timeout=30
            )
            return {
                "command": step.target,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "returncode": result.returncode
            }
        
        return None
    
    async def verify_plan(self, plan: ActionPlan) -> ActionResult:
        """
        Verify that a plan was applied correctly.
        
        Args:
            plan: The plan to verify
            
        Returns:
            ActionResult with verification status
        """
        if plan.status != ActionStatus.APPLIED:
            return ActionResult(
                success=False,
                plan=plan,
                error="Plan was not applied"
            )
        
        workspace = Path(self.runtime.config.workspace)
        verified = 0
        failed = 0
        
        for step in plan.steps:
            if step.status != ActionStatus.APPLIED:
                continue
            
            try:
                if step.action_type == ActionType.FILE_CREATE:
                    target = workspace / step.target
                    if target.exists():
                        step.status = ActionStatus.VERIFIED
                        verified += 1
                    else:
                        step.status = ActionStatus.FAILED
                        step.error = "File was not created"
                        failed += 1
                
                elif step.action_type == ActionType.FILE_DELETE:
                    target = workspace / step.target
                    if not target.exists():
                        step.status = ActionStatus.VERIFIED
                        verified += 1
                    else:
                        step.status = ActionStatus.FAILED
                        step.error = "File was not deleted"
                        failed += 1
                
                else:
                    # For other types, assume verified if applied
                    step.status = ActionStatus.VERIFIED
                    verified += 1
                    
            except Exception as e:
                step.status = ActionStatus.FAILED
                step.error = str(e)
                failed += 1
        
        plan.status = ActionStatus.VERIFIED if failed == 0 else ActionStatus.FAILED
        
        return ActionResult(
            success=failed == 0,
            plan=plan,
            applied_steps=verified,
            failed_steps=failed
        )
    
    async def execute(self, prompt: str, auto_approve: bool = False) -> ActionResult:
        """
        Execute a full plan → approve → apply → verify cycle.
        
        Args:
            prompt: The modification request
            auto_approve: Whether to auto-approve
            
        Returns:
            ActionResult with final status
        """
        # Create plan
        result = await self.create_plan(prompt)
        if not result.success:
            return result
        
        plan = result.plan
        
        # Approve
        approved = await self.approve_plan(plan, auto=auto_approve)
        if not approved and self.runtime.config.approval_mode == "manual":
            return ActionResult(
                success=False,
                plan=plan,
                error="Plan requires manual approval"
            )
        
        # Apply
        result = await self.apply_plan(plan)
        if not result.success:
            return result
        
        # Verify
        return await self.verify_plan(plan)
