"""
Escalation Pipeline for PraisonAI Agents.

Implements progressive escalation from direct response to full autonomous mode.
"""

import logging
import time
from typing import Any, Dict, List, Optional, Callable

from .types import (
    EscalationStage,
    EscalationConfig,
    EscalationResult,
    EscalationSignal,
    StageContext,
)
from .triggers import EscalationTrigger
from .doom_loop import DoomLoopDetector, RecoveryAction

logger = logging.getLogger(__name__)


class EscalationPipeline:
    """
    Progressive escalation pipeline for agent execution.
    
    Implements a staged approach to task execution:
    - Stage 0 (DIRECT): Immediate response without tools
    - Stage 1 (HEURISTIC): Tool selection based on local signals
    - Stage 2 (PLANNED): Lightweight planning with single LLM call
    - Stage 3 (AUTONOMOUS): Full autonomous loop with verification
    
    Example:
        pipeline = EscalationPipeline()
        
        # Analyze and execute
        result = await pipeline.execute("Refactor the auth module")
        
        # Or analyze first, then execute
        stage = pipeline.analyze("Simple question")
        result = await pipeline.execute_at_stage("Simple question", stage)
    """
    
    def __init__(
        self,
        config: Optional[EscalationConfig] = None,
        agent: Optional[Any] = None,
        tools: Optional[List[Any]] = None,
        checkpoint_service: Optional[Any] = None,
        on_stage_change: Optional[Callable[[EscalationStage, EscalationStage], None]] = None,
    ):
        """
        Initialize the escalation pipeline.
        
        Args:
            config: Pipeline configuration
            agent: Agent instance for execution
            tools: Available tools
            checkpoint_service: Service for checkpoints
            on_stage_change: Callback for stage transitions
        """
        self.config = config or EscalationConfig()
        self.agent = agent
        self.tools = tools or []
        self.checkpoint_service = checkpoint_service
        self.on_stage_change = on_stage_change
        
        # Components
        self.trigger = EscalationTrigger(self.config)
        self.doom_detector = DoomLoopDetector()
        
        # State
        self._current_context: Optional[StageContext] = None
    
    def analyze(
        self,
        prompt: str,
        context: Optional[Dict[str, Any]] = None
    ) -> EscalationStage:
        """
        Analyze prompt and recommend initial stage.
        
        Args:
            prompt: User prompt
            context: Optional context (workspace, history, etc.)
            
        Returns:
            Recommended starting stage
        """
        signals = self.trigger.analyze(prompt, context)
        return self.trigger.recommend_stage(signals)
    
    async def execute(
        self,
        prompt: str,
        context: Optional[Dict[str, Any]] = None,
        session_id: Optional[str] = None,
    ) -> EscalationResult:
        """
        Execute prompt with automatic escalation.
        
        Args:
            prompt: User prompt
            context: Optional context
            session_id: Optional session ID
            
        Returns:
            Execution result
        """
        # Analyze and get initial stage
        signals = self.trigger.analyze(prompt, context)
        initial_stage = self.trigger.recommend_stage(signals)
        
        return await self.execute_at_stage(
            prompt,
            initial_stage,
            signals=signals,
            context=context,
            session_id=session_id,
        )
    
    async def execute_at_stage(
        self,
        prompt: str,
        stage: EscalationStage,
        signals: Optional[set] = None,
        context: Optional[Dict[str, Any]] = None,
        session_id: Optional[str] = None,
    ) -> EscalationResult:
        """
        Execute prompt at specific stage.
        
        Args:
            prompt: User prompt
            stage: Stage to execute at
            signals: Pre-analyzed signals
            context: Optional context
            session_id: Optional session ID
            
        Returns:
            Execution result
        """
        start_time = time.time()
        
        # Initialize context
        self._current_context = StageContext(
            stage=stage,
            prompt=prompt,
            signals=signals or set(),
            session_id=session_id,
        )
        
        # Initialize doom loop detector
        self.doom_detector.start_session()
        
        # Track escalations
        escalations = 0
        deescalations = 0
        initial_stage = stage
        current_stage = stage
        
        response = ""
        errors: List[str] = []
        warnings: List[str] = []
        
        try:
            while True:
                # Execute at current stage
                stage_result = await self._execute_stage(current_stage, prompt)
                
                response = stage_result.get("response", "")
                success = stage_result.get("success", False)
                
                # Record action for doom loop detection
                self.doom_detector.record_action(
                    action_type=f"stage_{current_stage.name}",
                    args={"prompt": prompt[:100]},
                    result=response[:100] if response else None,
                    success=success,
                )
                
                # Check for doom loop
                if self.doom_detector.is_doom_loop():
                    recovery = self.doom_detector.get_recovery_action()
                    
                    if recovery == RecoveryAction.ABORT:
                        errors.append("Execution aborted due to doom loop")
                        break
                    elif recovery == RecoveryAction.ESCALATE_MODEL:
                        warnings.append("Escalating model due to loop detection")
                        # Model escalation would happen here
                    elif recovery == RecoveryAction.REQUEST_HELP:
                        warnings.append("Requesting user clarification")
                        response = "I'm having trouble completing this task. Could you provide more details?"
                        break
                    
                    if not self.doom_detector.increment_recovery():
                        errors.append("Max recovery attempts reached")
                        break
                    
                    self.doom_detector.apply_backoff()
                
                # Check if we should escalate
                if not success and self.config.auto_escalate:
                    if current_stage < EscalationStage.AUTONOMOUS:
                        new_stage = EscalationStage(current_stage + 1)
                        self._notify_stage_change(current_stage, new_stage)
                        current_stage = new_stage
                        escalations += 1
                        self._current_context.stage = current_stage
                        continue
                
                # Check if we should de-escalate
                if success and self.config.auto_deescalate:
                    if self._current_context.should_deescalate(self.config):
                        if current_stage > EscalationStage.DIRECT:
                            new_stage = EscalationStage(current_stage - 1)
                            self._notify_stage_change(current_stage, new_stage)
                            current_stage = new_stage
                            deescalations += 1
                
                # Success or can't escalate further
                if success or current_stage == EscalationStage.AUTONOMOUS:
                    break
                
                # Budget check
                elapsed = time.time() - start_time
                if elapsed > self.config.max_time_seconds:
                    warnings.append(f"Time budget exceeded ({elapsed:.1f}s)")
                    break
                
                if self._current_context.tool_calls > self.config.max_tool_calls:
                    warnings.append("Tool call budget exceeded")
                    break
        
        except Exception as e:
            errors.append(str(e))
            logger.exception("Error in escalation pipeline")
        
        # Build result
        elapsed = time.time() - start_time
        
        return EscalationResult(
            response=response,
            success=len(errors) == 0,
            initial_stage=initial_stage,
            final_stage=current_stage,
            escalations=escalations,
            deescalations=deescalations,
            signals=list(self._current_context.signals),
            steps_taken=len(self._current_context.steps),
            tool_calls=self._current_context.tool_calls,
            tokens_used=self._current_context.tokens_used,
            time_seconds=elapsed,
            checkpoint_id=self._current_context.checkpoint_ids[-1] if self._current_context.checkpoint_ids else None,
            files_modified=list(self._current_context.files_modified),
            errors=errors,
            warnings=warnings,
        )
    
    async def _execute_stage(
        self,
        stage: EscalationStage,
        prompt: str
    ) -> Dict[str, Any]:
        """
        Execute at a specific stage.
        
        Args:
            stage: Stage to execute
            prompt: User prompt
            
        Returns:
            Stage execution result
        """
        if stage == EscalationStage.DIRECT:
            return await self._execute_direct(prompt)
        elif stage == EscalationStage.HEURISTIC:
            return await self._execute_heuristic(prompt)
        elif stage == EscalationStage.PLANNED:
            return await self._execute_planned(prompt)
        elif stage == EscalationStage.AUTONOMOUS:
            return await self._execute_autonomous(prompt)
        else:
            return {"response": "", "success": False}
    
    async def _execute_direct(self, prompt: str) -> Dict[str, Any]:
        """
        Execute direct response (Stage 0).
        
        No tools, no planning - just direct LLM response.
        """
        if not self.agent:
            return {
                "response": "Agent not configured",
                "success": False,
            }
        
        try:
            # Direct chat without tools
            response = self.agent.chat(prompt)
            
            self._current_context.add_step(
                action="direct_response",
                result=response[:100] if response else "",
                success=True,
            )
            
            return {
                "response": response,
                "success": True,
            }
        except Exception as e:
            return {
                "response": str(e),
                "success": False,
            }
    
    async def _execute_heuristic(self, prompt: str) -> Dict[str, Any]:
        """
        Execute with heuristic tool selection (Stage 1).
        
        Uses local signals to select tools without extra LLM call.
        """
        if not self.agent:
            return {
                "response": "Agent not configured",
                "success": False,
            }
        
        try:
            # Select tools based on signals
            selected_tools = self._select_tools_heuristically()
            
            # Limit tools for heuristic stage
            selected_tools = selected_tools[:self.config.heuristic_max_tools]
            
            # Execute with selected tools
            if hasattr(self.agent, 'tools'):
                original_tools = self.agent.tools
                self.agent.tools = selected_tools
            
            try:
                response = self.agent.chat(prompt)
            finally:
                if hasattr(self.agent, 'tools'):
                    self.agent.tools = original_tools
            
            self._current_context.add_step(
                action="heuristic_response",
                result=response[:100] if response else "",
                success=True,
            )
            
            return {
                "response": response,
                "success": True,
            }
        except Exception as e:
            return {
                "response": str(e),
                "success": False,
            }
    
    async def _execute_planned(self, prompt: str) -> Dict[str, Any]:
        """
        Execute with lightweight planning (Stage 2).
        
        Single LLM call to create constrained plan, then execute.
        """
        if not self.agent:
            return {
                "response": "Agent not configured",
                "success": False,
            }
        
        try:
            # Create a simple plan prompt
            plan_prompt = f"""Create a brief plan (max {self.config.planned_max_steps} steps) to accomplish:
{prompt}

Respond with numbered steps, then execute them."""
            
            response = self.agent.chat(plan_prompt)
            
            self._current_context.add_step(
                action="planned_response",
                result=response[:100] if response else "",
                success=True,
            )
            
            return {
                "response": response,
                "success": True,
            }
        except Exception as e:
            return {
                "response": str(e),
                "success": False,
            }
    
    async def _execute_autonomous(self, prompt: str) -> Dict[str, Any]:
        """
        Execute full autonomous loop (Stage 3).
        
        Full tools + planning + verification + checkpoints.
        """
        if not self.agent:
            return {
                "response": "Agent not configured",
                "success": False,
            }
        
        try:
            # Create checkpoint if enabled
            if self.config.enable_checkpoints and self.checkpoint_service:
                try:
                    result = await self.checkpoint_service.save("Before autonomous execution")
                    if result.success:
                        self._current_context.checkpoint_ids.append(result.checkpoint.id)
                except Exception as e:
                    logger.warning(f"Failed to create checkpoint: {e}")
            
            # Full autonomous execution with all tools
            autonomous_prompt = f"""You are in autonomous mode. Complete this task thoroughly:
{prompt}

Use all available tools as needed. Verify your work before completing."""
            
            response = self.agent.chat(autonomous_prompt)
            
            self._current_context.add_step(
                action="autonomous_response",
                result=response[:100] if response else "",
                success=True,
            )
            
            # Mark progress
            self.doom_detector.mark_progress("autonomous_complete")
            
            return {
                "response": response,
                "success": True,
            }
        except Exception as e:
            return {
                "response": str(e),
                "success": False,
            }
    
    def _select_tools_heuristically(self) -> List[Any]:
        """
        Select tools based on detected signals.
        
        Returns:
            List of selected tools
        """
        if not self.tools:
            return []
        
        signals = self._current_context.signals
        selected = []
        
        # Map signals to tool categories
        tool_map = {
            EscalationSignal.FILE_REFERENCES: ["read_file", "list_files", "glob"],
            EscalationSignal.EDIT_INTENT: ["write_file", "edit_file", "patch"],
            EscalationSignal.TEST_INTENT: ["run_command", "shell"],
            EscalationSignal.BUILD_INTENT: ["run_command", "shell"],
            EscalationSignal.CODE_BLOCKS: ["read_file", "write_file"],
            EscalationSignal.REPO_CONTEXT: ["list_files", "grep", "glob"],
        }
        
        # Collect tool names to include
        tool_names = set()
        for signal in signals:
            if signal in tool_map:
                tool_names.update(tool_map[signal])
        
        # Filter tools
        for tool in self.tools:
            tool_name = getattr(tool, '__name__', str(tool)).lower()
            if any(name in tool_name for name in tool_names):
                selected.append(tool)
        
        # If no specific tools matched, return first few tools
        if not selected and self.tools:
            selected = self.tools[:3]
        
        return selected
    
    def _notify_stage_change(
        self,
        old_stage: EscalationStage,
        new_stage: EscalationStage
    ):
        """Notify about stage change."""
        logger.info(f"Stage change: {old_stage.name} -> {new_stage.name}")
        
        if self.on_stage_change:
            try:
                self.on_stage_change(old_stage, new_stage)
            except Exception as e:
                logger.warning(f"Stage change callback error: {e}")
    
    def get_current_stage(self) -> Optional[EscalationStage]:
        """Get current execution stage."""
        if self._current_context:
            return self._current_context.stage
        return None
    
    def get_context(self) -> Optional[StageContext]:
        """Get current execution context."""
        return self._current_context
