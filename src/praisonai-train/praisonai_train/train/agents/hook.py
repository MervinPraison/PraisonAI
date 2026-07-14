"""
Training Hook for Agent Runtime.

Provides hook-based injection of training suggestions into agent prompts.
This allows training data to be applied at runtime without modifying the Agent class.

Usage:
    from praisonai.train.agents import apply_training, remove_training
    from praisonaiagents import Agent
    
    agent = Agent(name="assistant", instructions="Be helpful")
    
    # Apply training from a session (uses best iteration by default)
    apply_training(agent, session_id="train-abc123")
    
    # Or apply training from a specific iteration
    apply_training(agent, session_id="train-abc123", iteration=2)
    
    # Or apply with a pre-loaded profile
    apply_training(agent, profile=my_profile)
    
    # Run the agent - training suggestions are automatically injected
    response = agent.start("Hello!")
    
    # Remove training when done
    remove_training(agent)
"""

import logging
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from praisonaiagents import Agent

from .models import TrainingProfile
from .storage import TrainingStorage

logger = logging.getLogger(__name__)

# Attribute name for storing hook ID on agent
_TRAINING_HOOK_ATTR = "_training_hook_id"


class TrainingHook:
    """
    Hook that injects training suggestions into agent prompts.
    
    This hook is registered on the BEFORE_AGENT event and modifies
    the prompt to include training guidance.
    
    Example:
        profile = TrainingProfile(
            agent_name="assistant",
            suggestions=["Be concise", "Use examples"],
            quality_score=8.5,
            summary="Focus on clarity",
            iteration_num=2,
            session_id="train-abc"
        )
        
        hook = TrainingHook(profile)
        # Hook is called automatically by the agent's hook system
    """
    
    def __init__(self, profile: TrainingProfile):
        """
        Initialize the training hook.
        
        Args:
            profile: The training profile with suggestions to inject
        """
        self.profile = profile
    
    def __call__(self, event):
        """
        Process the BEFORE_AGENT event.
        
        Modifies the prompt to include training guidance.
        
        Args:
            event: BeforeAgentInput event data
            
        Returns:
            HookResult with modified prompt
        """
        # Lazy import to avoid circular dependencies
        from praisonaiagents.hooks import HookResult
        
        # Build training guidance section
        guidance = self._build_guidance()
        
        # Get original prompt
        original_prompt = getattr(event, 'prompt', '') or ''
        
        # Append guidance to prompt
        modified_prompt = original_prompt + guidance
        
        return HookResult(
            decision="allow",
            modified_input={"prompt": modified_prompt},
            reason=f"Training guidance applied from session {self.profile.session_id}"
        )
    
    def _build_guidance(self) -> str:
        """
        Build the training guidance text to inject.
        
        Returns:
            Formatted guidance string
        """
        if not self.profile.suggestions:
            return ""
        
        lines = [
            "\n\n[TRAINING GUIDANCE]",
            f"Based on training session {self.profile.session_id} (iteration {self.profile.iteration_num}, score: {self.profile.quality_score}/10):",
        ]
        
        for suggestion in self.profile.suggestions:
            lines.append(f"- {suggestion}")
        
        if self.profile.summary:
            lines.append(f"\nSummary: {self.profile.summary}")
        
        lines.append("\nPlease follow these guidelines in your response.")
        
        return "\n".join(lines)


def apply_training(
    agent: "Agent",
    session_id: Optional[str] = None,
    iteration: Optional[int] = None,
    profile: Optional[TrainingProfile] = None,
) -> bool:
    """
    Apply training to an agent via BEFORE_AGENT hook.
    
    This function registers a hook that injects training suggestions
    into the agent's prompts at runtime.
    
    Args:
        agent: The agent to apply training to
        session_id: Training session ID to load from
        iteration: Specific iteration number to use (default: best score)
        profile: Pre-loaded TrainingProfile (alternative to session_id)
        
    Returns:
        True if training was applied successfully, False otherwise
        
    Raises:
        ValueError: If neither session_id nor profile is provided
        
    Example:
        # Apply best iteration from a session
        apply_training(agent, session_id="train-abc123")
        
        # Apply specific iteration
        apply_training(agent, session_id="train-abc123", iteration=2)
        
        # Apply with pre-loaded profile
        apply_training(agent, profile=my_profile)
    """
    if profile is None and session_id is None:
        raise ValueError("Either session_id or profile must be provided")
    
    # Load profile from session if not provided
    if profile is None:
        profile = _load_profile_from_session(
            session_id=session_id,
            iteration=iteration,
            agent_name=getattr(agent, 'name', 'agent'),
        )
        
        if profile is None:
            logger.warning(f"No training data found for session {session_id}")
            return False
    
    # Create the hook
    hook = TrainingHook(profile)
    
    # Get the hook registry from the agent
    try:
        # Lazy import
        from praisonaiagents.hooks import HookEvent
        
        registry = agent._hook_runner.registry
        
        # Register the hook
        hook_id = registry.register_function(
            event=HookEvent.BEFORE_AGENT,
            func=hook,
            name=f"training_hook_{profile.session_id}",
            description=f"Training guidance from session {profile.session_id}",
        )
        
        # Store hook ID on agent for later removal
        setattr(agent, _TRAINING_HOOK_ATTR, hook_id)
        
        logger.info(
            f"Applied training to agent '{agent.name}' from session "
            f"{profile.session_id} (iteration {profile.iteration_num}, "
            f"score: {profile.quality_score}/10)"
        )
        
        return True
        
    except Exception as e:
        logger.error(f"Failed to apply training: {e}")
        return False


def remove_training(agent: "Agent") -> bool:
    """
    Remove training hook from an agent.
    
    Args:
        agent: The agent to remove training from
        
    Returns:
        True if training was removed, False if no training was applied
        
    Example:
        remove_training(agent)
    """
    hook_id = getattr(agent, _TRAINING_HOOK_ATTR, None)
    
    if hook_id is None:
        logger.debug("No training hook found on agent")
        return False
    
    try:
        registry = agent._hook_runner.registry
        registry.unregister(hook_id)
        delattr(agent, _TRAINING_HOOK_ATTR)
        logger.info(f"Removed training from agent '{agent.name}'")
        return True
    except Exception as e:
        logger.error(f"Failed to remove training: {e}")
        return False


def _load_profile_from_session(
    session_id: str,
    iteration: Optional[int],
    agent_name: str,
) -> Optional[TrainingProfile]:
    """
    Load a TrainingProfile from a training session.
    
    Args:
        session_id: The training session ID
        iteration: Specific iteration number, or None for best
        agent_name: Name of the agent
        
    Returns:
        TrainingProfile or None if not found
    """
    try:
        storage = TrainingStorage(session_id=session_id)
        
        if not storage.storage_path.exists():
            logger.warning(f"Training session not found: {session_id}")
            return None
        
        report = storage.load_report()
        
        if report is None:
            logger.warning(f"No report found for session: {session_id}")
            return None
        
        # Get the iteration
        if iteration is not None:
            it = report.get_iteration(iteration)
            if it is None:
                logger.warning(f"Iteration {iteration} not found in session {session_id}")
                return None
        else:
            # Use best iteration
            it = report.get_best_iteration()
            if it is None:
                logger.warning(f"No iterations found in session {session_id}")
                return None
        
        # Create profile from iteration
        return TrainingProfile.from_iteration(
            iteration=it,
            agent_name=agent_name,
            session_id=session_id,
        )
        
    except Exception as e:
        logger.error(f"Failed to load training profile: {e}")
        return None


def get_training_profile(
    session_id: str,
    iteration: Optional[int] = None,
    agent_name: str = "agent",
) -> Optional[TrainingProfile]:
    """
    Get a training profile from a session without applying it.
    
    Useful for inspecting training data before applying.
    
    Args:
        session_id: The training session ID
        iteration: Specific iteration number, or None for best
        agent_name: Name to use for the profile
        
    Returns:
        TrainingProfile or None if not found
        
    Example:
        profile = get_training_profile("train-abc123")
        print(f"Score: {profile.quality_score}")
        print(f"Suggestions: {profile.suggestions}")
    """
    return _load_profile_from_session(session_id, iteration, agent_name)
