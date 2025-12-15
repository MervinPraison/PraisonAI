"""
ApprovalCallback for plan approval flow.

Provides approval functionality similar to:
- Cursor Plan Mode approval
- Claude Code plan approval
- Codex CLI /approvals

Features:
- Auto-approve option
- Custom approval functions
- Async support
- Plan modification during approval
"""

import asyncio
import inspect
import logging
from typing import Callable, Optional, Union, TYPE_CHECKING

if TYPE_CHECKING:
    from .plan import Plan

logger = logging.getLogger(__name__)


class ApprovalCallback:
    """
    Callback for plan approval flow.
    
    Handles the approval process for plans before execution.
    Can be configured for auto-approval or custom approval logic.
    
    Attributes:
        auto_approve: Whether to automatically approve all plans
        approve_fn: Custom approval function
        on_reject: Callback when plan is rejected
    """
    
    def __init__(
        self,
        auto_approve: bool = False,
        approve_fn: Optional[Callable[['Plan'], Union[bool, 'asyncio.Future']]] = None,
        on_reject: Optional[Callable[['Plan'], None]] = None
    ):
        """
        Initialize ApprovalCallback.
        
        Args:
            auto_approve: If True, automatically approve all plans
            approve_fn: Custom function to determine approval
                       Should return True to approve, False to reject
                       Can be sync or async
            on_reject: Optional callback when plan is rejected
        """
        self.auto_approve = auto_approve
        self.approve_fn = approve_fn
        self.on_reject = on_reject
        
    def __call__(self, plan: 'Plan') -> bool:
        """
        Synchronously check if plan is approved.
        
        Args:
            plan: Plan to check for approval
            
        Returns:
            True if approved, False if rejected
        """
        if self.auto_approve:
            logger.debug(f"Auto-approving plan: {plan.name}")
            plan.approve()
            return True
            
        if self.approve_fn is not None:
            # Check if function is async
            if inspect.iscoroutinefunction(self.approve_fn):
                # Run async function synchronously
                loop = asyncio.new_event_loop()
                try:
                    result = loop.run_until_complete(self.approve_fn(plan))
                finally:
                    loop.close()
            else:
                result = self.approve_fn(plan)
                
            if result:
                plan.approve()
                return True
            else:
                if self.on_reject:
                    self.on_reject(plan)
                return False
                
        # Default: require explicit approval (return False)
        logger.debug(f"Plan requires explicit approval: {plan.name}")
        return False
    
    async def async_call(self, plan: 'Plan') -> bool:
        """
        Asynchronously check if plan is approved.
        
        Args:
            plan: Plan to check for approval
            
        Returns:
            True if approved, False if rejected
        """
        if self.auto_approve:
            logger.debug(f"Auto-approving plan: {plan.name}")
            plan.approve()
            return True
            
        if self.approve_fn is not None:
            # Check if function is async
            if inspect.iscoroutinefunction(self.approve_fn):
                result = await self.approve_fn(plan)
            else:
                result = self.approve_fn(plan)
                
            if result:
                plan.approve()
                return True
            else:
                if self.on_reject:
                    self.on_reject(plan)
                return False
                
        # Default: require explicit approval (return False)
        logger.debug(f"Plan requires explicit approval: {plan.name}")
        return False
    
    @staticmethod
    def console_approval(plan: 'Plan') -> bool:
        """
        Interactive console approval.
        
        Displays the plan and prompts for approval.
        
        Args:
            plan: Plan to approve
            
        Returns:
            True if user approves, False otherwise
        """
        print("\n" + "=" * 60)
        print("PLAN APPROVAL REQUIRED")
        print("=" * 60)
        print(plan.to_markdown())
        print("=" * 60)
        
        while True:
            response = input("\nApprove this plan? [y/n/e(dit)]: ").strip().lower()
            
            if response in ['y', 'yes']:
                return True
            elif response in ['n', 'no']:
                return False
            elif response in ['e', 'edit']:
                print("\nPlan editing not implemented in console mode.")
                print("Please modify the plan programmatically and re-submit.")
                continue
            else:
                print("Please enter 'y' for yes, 'n' for no, or 'e' to edit.")
                
    @staticmethod
    def always_approve(plan: 'Plan') -> bool:
        """Always approve plans."""
        return True
    
    @staticmethod
    def always_reject(plan: 'Plan') -> bool:
        """Always reject plans."""
        return False
    
    @staticmethod
    def approve_if_small(plan: 'Plan', max_steps: int = 5) -> bool:
        """
        Approve plans with few steps automatically.
        
        Args:
            plan: Plan to check
            max_steps: Maximum number of steps to auto-approve
            
        Returns:
            True if plan has <= max_steps
        """
        return len(plan.steps) <= max_steps
    
    @staticmethod
    def approve_if_no_dangerous_tools(plan: 'Plan') -> bool:
        """
        Approve plans that don't use dangerous tools.
        
        Args:
            plan: Plan to check
            
        Returns:
            True if no dangerous tools are used
        """
        from . import RESTRICTED_TOOLS
        
        for step in plan.steps:
            for tool in step.tools:
                if tool in RESTRICTED_TOOLS:
                    logger.warning(f"Plan uses restricted tool: {tool}")
                    return False
                    
        return True


class InteractiveApproval:
    """
    Interactive approval handler with rich UI support.
    
    Provides a more sophisticated approval interface
    with plan editing capabilities.
    """
    
    def __init__(self, use_rich: bool = True):
        """
        Initialize InteractiveApproval.
        
        Args:
            use_rich: Whether to use Rich library for display
        """
        self.use_rich = use_rich
        self._rich_available = False
        
        if use_rich:
            try:
                from rich.console import Console
                from rich.panel import Panel
                from rich.prompt import Confirm
                self._rich_available = True
                self._console = Console()
            except ImportError:
                self._rich_available = False
                
    def __call__(self, plan: 'Plan') -> bool:
        """
        Display plan and get approval.
        
        Args:
            plan: Plan to approve
            
        Returns:
            True if approved
        """
        if self._rich_available:
            return self._rich_approval(plan)
        else:
            return ApprovalCallback.console_approval(plan)
            
    def _rich_approval(self, plan: 'Plan') -> bool:
        """Rich library approval display."""
        from rich.panel import Panel
        from rich.prompt import Confirm
        from rich.markdown import Markdown
        
        # Display plan
        md = Markdown(plan.to_markdown())
        self._console.print(Panel(md, title="[bold blue]Plan Approval Required[/bold blue]"))
        
        # Get approval
        approved = Confirm.ask("Approve this plan?")
        
        return approved
    
    async def async_call(self, plan: 'Plan') -> bool:
        """Async version of approval."""
        # For now, just call sync version
        # Could be extended for async UI frameworks
        return self(plan)
