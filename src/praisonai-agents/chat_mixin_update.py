"""
Helper methods for updating chat_mixin.py with proactive context overflow protection.

These methods will be integrated into the chat_mixin.py file.
"""

def _compute_context_budget_and_route(self, messages, tools=None, system_prompt=None):
    """
    Compute context budget and determine proactive route BEFORE LLM call.
    
    Replaces the old opt-in reactive approach with proactive budget checking.
    
    Returns:
        tuple: (route, compacted_messages) where route is from CompactionRoute enum
    """
    from ..context.policy import get_default_policy, CompactionRoute
    from ..compaction import ContextCompactor
    from ..hooks import HookEvent as _HookEvent
    import logging
    
    # Get execution config and policy
    _execution_cfg = getattr(self, 'execution', None)
    
    # Determine if context compaction is enabled and what policy to use
    context_compaction = True  # New default
    policy = None
    
    if _execution_cfg:
        compaction_setting = getattr(_execution_cfg, 'context_compaction', True)
        if compaction_setting is False:
            # Explicitly disabled - use old reactive approach
            return CompactionRoute.FITS, messages
        elif compaction_setting is True:
            # Use default policy
            policy = get_default_policy()
        else:
            # Custom policy provided
            policy = compaction_setting
    else:
        # No execution config - use safe default
        policy = get_default_policy()
    
    # Get model name for context window lookup
    model_name = self.llm if isinstance(self.llm, str) else "gpt-4o-mini"
    
    # Compute budget using the policy
    budget_result = policy.compute_context_budget(
        messages=messages,
        model=model_name,
        tools=tools,
        system_prompt=system_prompt
    )
    
    # Log budget analysis if enabled
    if getattr(self, '_verbose_context', False):
        logging.info(
            f"[context-budget] {self.name}: {budget_result.current_tokens} tokens, "
            f"{budget_result.utilization:.1%} utilization, route: {budget_result.route.value}"
        )
    
    # Handle the routing decision
    if budget_result.route == CompactionRoute.FITS:
        return CompactionRoute.FITS, messages
    
    # Need some form of compaction - get max tokens for compactor
    max_tokens = getattr(_execution_cfg, 'max_context_tokens', None) if _execution_cfg else None
    if max_tokens is None:
        # Use 90% of available tokens as max to leave room for output
        max_tokens = int(budget_result.available_tokens * 0.9)
    
    # Create compactor with policy-driven settings
    compactor = ContextCompactor(
        max_tokens=max_tokens,
        target_tokens=int(max_tokens * policy.target_utilization),
        preserve_recent=policy.preserve_last_n_turns
    )
    
    # Apply compaction based on route
    if budget_result.route == CompactionRoute.COMPACT_NEEDED:
        return self._apply_compaction(messages, compactor, policy)
    elif budget_result.route == CompactionRoute.TRUNCATE_TOOLS:
        return self._apply_tool_truncation(messages, compactor, policy)
    elif budget_result.route == CompactionRoute.COMPACT_THEN_TRUNCATE:
        # First try compaction
        route, compacted_messages = self._apply_compaction(messages, compactor, policy)
        # If still over budget, also truncate tools
        if compactor.needs_compaction(compacted_messages):
            return self._apply_tool_truncation(compacted_messages, compactor, policy)
        return route, compacted_messages
    
    return CompactionRoute.FITS, messages


def _apply_compaction(self, messages, compactor, policy):
    """Apply standard context compaction."""
    from ..compaction.strategy import CompactionStrategy as LegacyStrategy
    from ..hooks import HookEvent as _HookEvent
    import logging
    
    # Map policy strategy to compactor strategy
    strategy_map = {
        "truncate": LegacyStrategy.TRUNCATE,
        "summarise": LegacyStrategy.SUMMARIZE,
        "drop_oldest_tools": LegacyStrategy.PRUNE,
        "sliding_window": LegacyStrategy.SLIDING,
    }
    
    compactor.strategy = strategy_map.get(policy.strategy.value, LegacyStrategy.PRUNE)
    
    # Execute hooks
    try:
        self._hook_runner.execute_sync(_HookEvent.BEFORE_COMPACTION, None)
    except Exception as e:
        logging.warning(f"BEFORE_COMPACTION hook failed: {e}")
        if getattr(self, '_strict_hooks', False):
            raise
    
    # Perform compaction
    compacted_msgs, result = compactor.compact(messages)
    
    logging.info(
        f"[proactive-compaction] {self.name}: {result.original_tokens}→{result.compacted_tokens} tokens "
        f"({result.messages_removed} messages removed, strategy: {policy.strategy.value})"
    )
    
    try:
        self._hook_runner.execute_sync(_HookEvent.AFTER_COMPACTION, result)
    except Exception as e:
        logging.warning(f"AFTER_COMPACTION hook failed: {e}")
        if getattr(self, '_strict_hooks', False):
            raise
    
    from ..context.policy import CompactionRoute
    return CompactionRoute.COMPACT_NEEDED, compacted_msgs


def _apply_tool_truncation(self, messages, compactor, policy):
    """Apply targeted tool output truncation."""
    from ..context.policy import CompactionRoute
    import logging
    
    # Create a copy to avoid modifying original
    truncated_msgs = []
    
    for msg in messages:
        if msg.get("role") == "tool" or msg.get("tool_call_id"):
            content = msg.get("content", "")
            if isinstance(content, str) and len(content) > 1000:
                # Truncate large tool outputs
                truncated_msg = msg.copy()
                head = content[:300]
                tail = content[-200:] if len(content) > 500 else ""
                truncated_msg["content"] = f"{head}\n...[truncated {len(content):,} chars for context budget]...\n{tail}"
                truncated_msgs.append(truncated_msg)
                continue
        
        truncated_msgs.append(msg)
    
    original_tokens = compactor.count_total_tokens(messages)
    new_tokens = compactor.count_total_tokens(truncated_msgs)
    
    logging.info(
        f"[tool-truncation] {self.name}: {original_tokens}→{new_tokens} tokens "
        f"(truncated large tool outputs)"
    )
    
    return CompactionRoute.TRUNCATE_TOOLS, truncated_msgs