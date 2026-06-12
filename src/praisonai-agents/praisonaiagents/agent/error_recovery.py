"""
Unified error recovery logic for both sync and async chat completion.

This module extracts the common error classification and recovery logic
from chat_mixin.py to eliminate duplication between sync and async handlers.
"""

import logging
import time
import asyncio
from typing import Union, Any, Dict, Optional, List
from ..errors import LLMError
from ..llm.error_classifier import classify_llm_error


class ErrorRecoveryHandler:
    """
    Unified error recovery handler for both sync and async chat operations.
    
    Eliminates duplication between _chat_completion and _handle_async_llm_error
    by providing shared classification and recovery logic.
    """
    
    def __init__(self, agent):
        """Initialize with agent instance for context."""
        self.agent = agent
    
    def classify_error(
        self, 
        exc: Exception,
        messages: List[Dict],
        retry_depth: int = 0
    ) -> 'LLMErrorClassification':
        """
        Classify error and return structured recovery hints.
        
        Common logic for both sync and async error handling.
        """
        model_name = self.agent.llm if isinstance(self.agent.llm, str) else "unknown"
        
        # Determine provider from model name
        provider = "openai"  # Default assumption
        if "claude" in model_name.lower() or "anthropic" in model_name.lower():
            provider = "anthropic"
        elif "azure" in model_name.lower():
            provider = "azure"
        
        # Get token counts for context-aware classification
        prompt_tokens = 0
        context_length = 0
        try:
            from ..context.tokens import estimate_messages_tokens
            prompt_tokens = estimate_messages_tokens(messages)
            context_length = prompt_tokens
        except Exception:
            pass  # Token estimation failed, continue without counts
        
        # Classify error with structured recovery hints
        return classify_llm_error(
            exc,
            provider=provider,
            model=model_name,
            prompt_tokens=prompt_tokens,
            context_length=context_length,
            retry_depth=retry_depth,
        )
    
    def handle_context_compression(
        self, 
        classification: 'LLMErrorClassification',
        messages: List[Dict],
        model_name: str
    ) -> Optional[List[Dict]]:
        """
        Handle context compression recovery.
        
        Returns compressed messages if compression succeeds, None if it fails.
        """
        if not (classification.should_compress_context and self.agent.context_manager):
            return None
        
        try:
            from ..context.budgeter import get_model_limit
            model_limit = get_model_limit(model_name)
            target = int(model_limit * 0.7)  # Target 70% of limit for safety
            
            # Apply emergency truncation
            truncated_messages = self.agent.context_manager.emergency_truncate(messages, target)
            
            logging.info(f"[{self.agent.name}] {classification.user_message}")
            return truncated_messages
            
        except Exception as compression_error:
            logging.error(f"[{self.agent.name}] Context compression failed: {compression_error}")
            return None
    
    def handle_recovery_actions(self, classification: 'LLMErrorClassification') -> Dict[str, Any]:
        """
        Handle recovery actions and return action results.
        
        Returns dict with action_taken and should_retry flags.
        """
        result = {"action_taken": False, "should_retry": False}
        
        if classification.should_rotate_credential:
            # TODO: Implement credential rotation when available
            logging.warning(f"[{self.agent.name}] {classification.user_message} (credential rotation not yet implemented)")
            result["action_taken"] = True
            # Don't retry without actual credential rotation
            
        elif classification.should_fallback_model:
            # TODO: Implement model fallback when available
            logging.warning(f"[{self.agent.name}] {classification.user_message} (model fallback not yet implemented)")
            result["action_taken"] = True
            # Don't retry without actual model fallback
            
        elif classification.is_retryable and classification.backoff_seconds > 0:
            result["should_retry"] = True
            result["action_taken"] = True
        
        return result
    
    def create_llm_error(
        self,
        exc: Exception,
        classification: 'LLMErrorClassification',
        model_name: str
    ) -> LLMError:
        """
        Create enriched LLMError with classification context.
        
        Common error creation logic for both sync and async paths.
        """
        session_id = getattr(self.agent, '_session_id', 'unknown')
        
        # Include remediation hints for unimplemented recovery actions
        user_message = classification.user_message
        if classification.should_rotate_credential:
            user_message += " Credential rotation is not yet implemented."
        if classification.should_fallback_model:
            user_message += " Model fallback is not yet implemented."
        
        return LLMError(
            str(exc),
            model_name=model_name,
            agent_id=self.agent.name,
            is_retryable=classification.is_retryable,
            context={
                "session_id": session_id,
                "error_category": classification.error_category,
                "user_message": user_message,
            },
        )
    
    def call_error_hook(self, error: LLMError) -> None:
        """
        Call error hook if available for error interception.
        
        Common hook calling logic for both sync and async paths.
        """
        if hasattr(self.agent, 'on_error') and self.agent.on_error:
            try:
                self.agent.on_error(error)
            except Exception as hook_error:
                logging.debug(f"Error in on_error hook: {hook_error}")
    
    def sync_retry_delay(self, backoff_seconds: float) -> None:
        """Apply retry delay in sync context."""
        time.sleep(backoff_seconds)
    
    async def async_retry_delay(self, backoff_seconds: float) -> None:
        """Apply retry delay in async context."""
        await asyncio.sleep(backoff_seconds)


def handle_sync_llm_error(
    agent,
    exc: Exception,
    messages: List[Dict],
    retry_depth: int = 0,
    **chat_params
):
    """
    Handle LLM error in sync context using unified recovery logic.
    
    This replaces the inline error handling in _chat_completion method.
    """
    handler = ErrorRecoveryHandler(agent)
    
    # Classify the error
    classification = handler.classify_error(exc, messages, retry_depth)
    model_name = agent.llm if isinstance(agent.llm, str) else "unknown"
    
    # Try context compression if needed
    compressed_messages = handler.handle_context_compression(classification, messages, model_name)
    if compressed_messages is not None and retry_depth < 2:
        # Retry with compressed context
        return agent._chat_completion(
            compressed_messages, 
            _retry_depth=retry_depth + 1,
            **chat_params
        )
    
    # Handle other recovery actions
    recovery_result = handler.handle_recovery_actions(classification)
    
    # Handle retry with backoff
    if recovery_result["should_retry"] and retry_depth < 2:
        logging.info(f"[{agent.name}] {classification.user_message} (waiting {classification.backoff_seconds:.1f}s)")
        handler.sync_retry_delay(classification.backoff_seconds)
        return agent._chat_completion(
            messages, 
            _retry_depth=retry_depth + 1,
            **chat_params
        )
    
    # Create and raise enriched error
    error = handler.create_llm_error(exc, classification, model_name)
    handler.call_error_hook(error)
    raise error


async def handle_async_llm_error(
    agent,
    exc: Exception,
    messages: List[Dict],
    retry_depth: int = 0,
    **chat_params
):
    """
    Handle LLM error in async context using unified recovery logic.
    
    This replaces the _handle_async_llm_error method.
    """
    handler = ErrorRecoveryHandler(agent)
    
    # Classify the error
    classification = handler.classify_error(exc, messages, retry_depth)
    model_name = agent.llm if isinstance(agent.llm, str) else "unknown"
    
    # Try context compression if needed
    compressed_messages = handler.handle_context_compression(classification, messages, model_name)
    if compressed_messages is not None and retry_depth < 2:
        # Retry with compressed context
        try:
            return await agent._execute_unified_achat_completion(
                compressed_messages,
                **chat_params
            )
        except Exception as retry_error:
            return await handle_async_llm_error(
                agent, retry_error, compressed_messages, retry_depth + 1, **chat_params
            )
    
    # Handle other recovery actions
    recovery_result = handler.handle_recovery_actions(classification)
    
    # Handle retry with backoff
    if recovery_result["should_retry"] and retry_depth < 2:
        logging.info(f"[{agent.name}] {classification.user_message} (waiting {classification.backoff_seconds:.1f}s)")
        await handler.async_retry_delay(classification.backoff_seconds)
        try:
            return await agent._execute_unified_achat_completion(
                messages,
                **chat_params
            )
        except Exception as retry_error:
            return await handle_async_llm_error(
                agent, retry_error, messages, retry_depth + 1, **chat_params
            )
    
    # Create and raise enriched error
    error = handler.create_llm_error(exc, classification, model_name)
    handler.call_error_hook(error)
    raise error