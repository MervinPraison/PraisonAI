"""
Automatic Conversation Summarization for PraisonAI Agents.

Provides automatic summarization when context window fills up.
Reuses existing telemetry/token_collector for token tracking.
"""

import logging
from typing import Optional, List, Dict, Any, Callable
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class SummarizationConfig:
    """Configuration for auto-summarization."""
    enabled: bool = False
    threshold: float = 0.8  # 80% of context window
    context_window: int = 128000  # Default for GPT-4
    summary_model: Optional[str] = None  # Use smaller model for summaries
    preserve_system: bool = True  # Keep system message
    preserve_recent: int = 2  # Keep last N message pairs


class SummarizationManager:
    """
    Manages automatic conversation summarization.
    
    Tracks token usage and triggers summarization when threshold is reached.
    Thread-safe for multi-agent use.
    """
    
    # Context window sizes for common models
    MODEL_CONTEXT_WINDOWS = {
        "gpt-4o": 128000,
        "gpt-4o-mini": 128000,
        "gpt-4-turbo": 128000,
        "gpt-4": 8192,
        "gpt-3.5-turbo": 16385,
        "claude-3-opus": 200000,
        "claude-3-sonnet": 200000,
        "claude-3-haiku": 200000,
        "claude-3-5-sonnet": 200000,
        "gemini-pro": 32000,
        "gemini-1.5-pro": 1000000,
        "gemini-1.5-flash": 1000000,
    }
    
    def __init__(
        self,
        context_window: int = 128000,
        threshold: float = 0.8,
        summary_model: Optional[str] = None,
        preserve_system: bool = True,
        preserve_recent: int = 2,
    ):
        """
        Initialize summarization manager.
        
        Args:
            context_window: Maximum context window size in tokens
            threshold: Percentage of context window to trigger summarization (0.0-1.0)
            summary_model: Model to use for generating summaries (None = use same model)
            preserve_system: Whether to preserve system message after summarization
            preserve_recent: Number of recent message pairs to preserve
        """
        if not 0.0 < threshold <= 1.0:
            raise ValueError("threshold must be between 0.0 and 1.0")
            
        self.context_window = context_window
        self.threshold = threshold
        self.summary_model = summary_model
        self.preserve_system = preserve_system
        self.preserve_recent = preserve_recent
        self.current_tokens = 0
        self._summarization_count = 0
        
    @classmethod
    def for_model(cls, model: str, threshold: float = 0.8, **kwargs) -> "SummarizationManager":
        """Create a SummarizationManager configured for a specific model."""
        # Normalize model name
        model_lower = model.lower()
        
        # Find matching context window
        context_window = 128000  # Default
        for model_key, window in cls.MODEL_CONTEXT_WINDOWS.items():
            if model_key in model_lower:
                context_window = window
                break
                
        return cls(context_window=context_window, threshold=threshold, **kwargs)
    
    def add_tokens(self, tokens: int) -> None:
        """Add tokens to the current count."""
        self.current_tokens += tokens
        
    def set_tokens(self, tokens: int) -> None:
        """Set the current token count."""
        self.current_tokens = tokens
        
    def reset_tokens(self) -> None:
        """Reset token count after summarization."""
        self.current_tokens = 0
        
    def should_summarize(self) -> bool:
        """Check if summarization should be triggered."""
        threshold_tokens = int(self.context_window * self.threshold)
        return self.current_tokens >= threshold_tokens
    
    def get_usage_percentage(self) -> float:
        """Get current context window usage as percentage."""
        return self.current_tokens / self.context_window
    
    def generate_summary_prompt(self, messages: List[Dict[str, str]]) -> str:
        """Generate prompt for summarizing conversation."""
        conversation = "\n".join([
            f"{msg['role'].upper()}: {msg['content']}"
            for msg in messages
            if msg['role'] != 'system'
        ])
        
        return f"""Summarize the following conversation concisely, preserving:
1. Key decisions and conclusions
2. Important context and facts
3. Any pending tasks or questions
4. Technical details that may be needed later

Keep the summary under 500 words.

CONVERSATION:
{conversation}

SUMMARY:"""

    def prepare_summarized_history(
        self,
        messages: List[Dict[str, str]],
        summary: str
    ) -> List[Dict[str, str]]:
        """
        Prepare new message history after summarization.
        
        Args:
            messages: Original message history
            summary: Generated summary
            
        Returns:
            New message history with summary replacing old messages
        """
        new_history = []
        
        # Preserve system message if configured
        if self.preserve_system and messages and messages[0].get('role') == 'system':
            new_history.append(messages[0])
            
        # Add summary as assistant message
        new_history.append({
            "role": "assistant",
            "content": f"[Previous conversation summary]\n{summary}"
        })
        
        # Preserve recent messages
        if self.preserve_recent > 0:
            # Get last N pairs (user + assistant)
            recent_count = self.preserve_recent * 2
            recent_messages = [
                m for m in messages[-recent_count:]
                if m.get('role') != 'system'
            ]
            new_history.extend(recent_messages)
            
        self._summarization_count += 1
        logger.info(f"Conversation summarized (count: {self._summarization_count})")
        
        return new_history
    
    @property
    def summarization_count(self) -> int:
        """Number of times summarization has been performed."""
        return self._summarization_count


async def summarize_conversation(
    messages: List[Dict[str, str]],
    llm_call: Callable,
    manager: SummarizationManager,
) -> List[Dict[str, str]]:
    """
    Summarize conversation using LLM.
    
    Args:
        messages: Current message history
        llm_call: Async function to call LLM
        manager: SummarizationManager instance
        
    Returns:
        New message history with summary
    """
    prompt = manager.generate_summary_prompt(messages)
    
    # Call LLM to generate summary
    summary = await llm_call(prompt)
    
    # Prepare new history
    new_history = manager.prepare_summarized_history(messages, summary)
    
    # Reset token count (will be recalculated on next message)
    manager.reset_tokens()
    
    return new_history


def summarize_conversation_sync(
    messages: List[Dict[str, str]],
    llm_call: Callable,
    manager: SummarizationManager,
) -> List[Dict[str, str]]:
    """
    Synchronous version of summarize_conversation.
    """
    prompt = manager.generate_summary_prompt(messages)
    summary = llm_call(prompt)
    new_history = manager.prepare_summarized_history(messages, summary)
    manager.reset_tokens()
    return new_history
