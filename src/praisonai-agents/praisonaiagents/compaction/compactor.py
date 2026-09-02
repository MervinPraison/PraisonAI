"""
Context Compactor for PraisonAI Agents.

Manages context window by compacting messages when needed.
"""

import re
import threading
from typing import List, Dict, Any, Optional, Callable, Awaitable, Tuple
import asyncio

from .config import CompactionConfig, COMPACTION_PREFIX, SUMMARY_TEMPLATE
from .strategy import CompactionStrategy
from .result import CompactionResult
from .protocols import ToolResultPrunerProtocol, MessageFormatterProtocol, SummaryBuilderProtocol


# Cache for the one-time offline-safe tiktoken probe (see estimate_tokens).
# None = not yet probed; True/False = probe result. Guarded by a lock so a
# single worker thread performs the probe even under concurrent compaction.
_ACCURATE_TOKENISER_STATE: Optional[bool] = None
_ACCURATE_TOKENISER_LOCK = threading.Lock()
# Seconds to wait for tiktoken's first init. A local (cached) vocab loads well
# under this; a network download does not, so we fall back without blocking.
_ACCURATE_TOKENISER_PROBE_TIMEOUT = 2.0


def _accurate_tokeniser_available() -> bool:
    """Return True if tiktoken can tokenise offline without a blocking download.

    tiktoken fetches its BPE vocab from the network on first use, which can hang
    on network-isolated hosts (e.g. CI). We probe exactly once in a short-lived
    daemon thread: if the accurate tokeniser initialises within the timeout it is
    used thereafter; otherwise we cache a permanent fallback to the heuristic.
    """
    global _ACCURATE_TOKENISER_STATE
    if _ACCURATE_TOKENISER_STATE is not None:
        return _ACCURATE_TOKENISER_STATE

    with _ACCURATE_TOKENISER_LOCK:
        if _ACCURATE_TOKENISER_STATE is not None:
            return _ACCURATE_TOKENISER_STATE

        result: List[bool] = []

        def _probe() -> None:
            try:
                from ..context.tokens import estimate_tokens_accurate
                # Force real tokeniser init; heuristic fallback returns >0 too,
                # but a network download would block here (bounded by the thread
                # timeout below rather than hanging the caller).
                estimate_tokens_accurate("probe", "gpt-4")
                result.append(True)
            except Exception:
                result.append(False)

        probe_thread = threading.Thread(target=_probe, daemon=True)
        probe_thread.start()
        probe_thread.join(_ACCURATE_TOKENISER_PROBE_TIMEOUT)

        # Timed out (likely a network download) or probe reported unavailable.
        _ACCURATE_TOKENISER_STATE = bool(result and result[0])
        return _ACCURATE_TOKENISER_STATE


class ContextCompactor:
    """
    Compacts conversation context to fit within token limits.
    
    Example:
        compactor = ContextCompactor(max_tokens=8000)
        
        # Check if compaction needed
        if compactor.needs_compaction(messages):
            result = compactor.compact(messages)
            messages = result.messages
    """
    
    def __init__(
        self,
        max_tokens: int = 8000,
        target_tokens: Optional[int] = None,
        strategy: CompactionStrategy = CompactionStrategy.TRUNCATE,
        preserve_system: bool = True,
        preserve_recent: int = 5,
        config: Optional[CompactionConfig] = None,
        llm_summarize_fn: Optional[Callable[[str], Awaitable[str]]] = None,
        tool_pruner: Optional[ToolResultPrunerProtocol] = None,
        message_formatter: Optional[MessageFormatterProtocol] = None,
        summary_builder: Optional[SummaryBuilderProtocol] = None
    ):
        """
        Initialize the compactor.
        
        Args:
            max_tokens: Maximum tokens before compaction
            target_tokens: Target tokens after compaction
            strategy: Compaction strategy to use
            preserve_system: Keep system messages
            preserve_recent: Number of recent messages to preserve
            config: Optional CompactionConfig for advanced settings
            llm_summarize_fn: Async function to call LLM for summarization
            tool_pruner: Protocol implementation for tool result pruning
            message_formatter: Protocol implementation for message formatting
            summary_builder: Protocol implementation for summary building
        """
        # Use provided config or create default
        self.config = config or CompactionConfig(
            max_tokens=max_tokens,
            target_tokens=target_tokens or int(max_tokens * 0.75),
            preserve_system=preserve_system,
            preserve_recent=preserve_recent
        )
        
        # Set instance attributes from config to ensure consistency
        self.max_tokens = self.config.max_tokens
        self.target_tokens = self.config.target_tokens
        self.strategy = strategy
        self.preserve_system = self.config.preserve_system
        self.preserve_recent = self.config.preserve_recent
        self.llm_summarize_fn = llm_summarize_fn
        
        # Protocol implementations (defaults to None - no heavy implementations in core)
        self.tool_pruner = tool_pruner
        self.message_formatter = message_formatter
        # Default the structured summary builder when the config asks for the
        # phase-aware template but no builder was injected, so
        # `_build_structured_summary` renders SUMMARY_TEMPLATE instead of the
        # "Summary of N messages" stub. The builder is deterministic and
        # dependency-free, so this stays offline-safe and zero-overhead.
        if summary_builder is None and getattr(self.config, "structured_template", False):
            from .summary_builder import DefaultSummaryBuilder

            summary_builder = DefaultSummaryBuilder(
                llm_summarize_fn=self.llm_summarize_fn
            )
        self.summary_builder = summary_builder
        
        # Anti-thrashing state tracking
        self._last_savings_pct: float = 100.0  # Start high to allow first compaction
        self._low_savings_streak: int = 0
        # Token count at the moment the streak reached its cap. The guard is
        # released once the conversation grows materially past this, so a
        # compactor that once could not shrink the context is never disabled
        # for the rest of the session.
        self._low_savings_tokens: int = 0

        # Iterative summary state
        self._previous_summary: Optional[str] = None
        self._previous_summary_global_idx: int = 0
        
        # Reset state tracking for each compact() call
        self._used_previous_summary: bool = False
    
    def estimate_tokens(self, text: str) -> int:
        """
        Estimate token count for text.

        Uses an accurate tokeniser (tiktoken) when it is available **offline**;
        otherwise falls back to a fast character heuristic.

        tiktoken downloads its BPE vocabulary from the network on first use, and
        that download can block indefinitely on network-isolated hosts (e.g. CI).
        To keep token counting fast and offline-safe, the accurate path is probed
        exactly once in a short-lived worker thread: if the tokeniser is already
        available locally it is used, otherwise we permanently fall back to the
        heuristic without ever blocking the hot path.
        """
        if not text:
            return 0
        if _accurate_tokeniser_available():
            try:
                from ..context.tokens import estimate_tokens_accurate
                return estimate_tokens_accurate(
                    text, getattr(self.config, "model", None) or "gpt-4"
                )
            except Exception:
                pass
        from ..context.tokens import estimate_tokens_heuristic
        return estimate_tokens_heuristic(text)

    def count_message_tokens(self, message: Dict[str, Any]) -> int:
        """Count tokens in a message, including tool_calls payloads."""
        total = 0
        content = message.get("content", "")
        if isinstance(content, str):
            total += self.estimate_tokens(content)
        elif isinstance(content, list):
            # Handle multi-part content
            for part in content:
                if isinstance(part, dict):
                    total += self.estimate_tokens(str(part.get("text", "")))
                else:
                    total += self.estimate_tokens(str(part))

        # Count tool_calls (function name + arguments) which are otherwise ignored
        for tool_call in (message.get("tool_calls") or []):
            if isinstance(tool_call, dict):
                func = tool_call.get("function", {})
                total += self.estimate_tokens(str(func))

        return total
    
    def count_total_tokens(self, messages: List[Dict[str, Any]]) -> int:
        """Count total tokens in messages."""
        return sum(self.count_message_tokens(m) for m in messages)
    
    def needs_compaction(self, messages: List[Dict[str, Any]]) -> bool:
        """
        Check if messages need compaction with anti-thrashing protection.
        
        Returns False if:
        - Token count is below threshold
        - We've had too many consecutive low-savings attempts
        """
        total_tokens = self.count_total_tokens(messages)
        if total_tokens <= self.max_tokens:
            return False

        # Anti-thrashing: skip if we've had too many low-savings attempts,
        # unless the conversation has grown enough to be worth re-testing.
        if self._should_skip_low_savings(total_tokens):
            return False

        return True

    #: Growth factor that releases the anti-thrashing guard. A conversation
    #: 25% larger than the one we gave up on is materially different input,
    #: so the earlier "not worth compacting" verdict is re-tested.
    _LOW_SAVINGS_RETRY_GROWTH = 1.25

    def _should_skip_low_savings(self, original_tokens: int) -> bool:
        """Whether the anti-thrashing guard should skip this pass.

        The guard stops a compactor that cannot shrink a conversation from
        burning a summarisation call every turn. It must not be permanent:
        ``_low_savings_streak`` is only cleared *after* a compaction actually
        runs, so a compactor that trips the cap would otherwise skip forever
        and let the context grow without bound -- the precise opposite of what
        the guard is for.

        Growth past the size we gave up on is new evidence, so the verdict is
        retried and the streak reset.
        """
        if self._low_savings_streak < self.config.max_consecutive_low_savings:
            return False
        if self._low_savings_tokens and original_tokens >= (
            self._low_savings_tokens * self._LOW_SAVINGS_RETRY_GROWTH
        ):
            self._low_savings_streak = 0
            self._low_savings_tokens = 0
            return False
        return True

    def _record_savings_outcome(self, savings_pct: float, original_tokens: int) -> None:
        """Update anti-thrashing state after a completed compaction pass."""
        self._last_savings_pct = savings_pct
        if savings_pct >= self.config.min_savings_pct:
            self._low_savings_streak = 0
            self._low_savings_tokens = 0
            return
        self._low_savings_streak += 1
        if self._low_savings_streak >= self.config.max_consecutive_low_savings:
            # Remember the size we gave up at, so growth can release the guard.
            self._low_savings_tokens = original_tokens
    
    def compact(
        self,
        messages: List[Dict[str, Any]],
        focus_topic: str = ""
    ) -> tuple[List[Dict[str, Any]], CompactionResult]:
        """
        Compact messages to fit within token limit (synchronous version).
        
        For LLM_SUMMARIZE strategy, falls back to naive summarization if no LLM function provided.
        Use compact_async for proper LLM integration.
        
        Args:
            messages: List of messages to compact
            focus_topic: Optional topic to focus on during summarization
            
        Returns:
            Tuple of (compacted messages, result)
        """
        # Reset state for this compaction call
        self._used_previous_summary = False
        
        original_tokens = self.count_total_tokens(messages)
        
        if original_tokens <= self.max_tokens:
            result = CompactionResult(
                original_tokens=original_tokens,
                compacted_tokens=original_tokens,
                messages_removed=0,
                messages_kept=len(messages),
                strategy_used=self.strategy
            )
            result.calculate_savings_pct()
            return messages, result

        # Anti-thrashing: if prior passes yielded too little savings, skip and
        # surface it on the result so callers can detect the skip. Without this
        # the documented ``was_skipped_due_to_low_savings`` flag never fired.
        if self._should_skip_low_savings(original_tokens):
            result = CompactionResult(
                original_tokens=original_tokens,
                compacted_tokens=original_tokens,
                messages_removed=0,
                messages_kept=len(messages),
                strategy_used=self.strategy,
                was_skipped_due_to_low_savings=True,
            )
            result.calculate_savings_pct()
            return messages, result

        # Apply tool result deduplication pre-pass if enabled
        processed_messages = messages
        tool_results_pruned = 0
        if self.config.tool_prune_before_summarise and self.tool_pruner:
            processed_messages, tool_results_pruned = self.tool_pruner.prune(
                messages, 
                self.config.max_tool_result_size
            )
        
        # Skip early exit - proceed with full compaction strategy
        # Anti-thrashing check will be applied after strategy runs
        
        if self.strategy == CompactionStrategy.TRUNCATE:
            compacted = self._truncate(processed_messages)
        elif self.strategy == CompactionStrategy.SLIDING:
            compacted = self._sliding_window(processed_messages)
        elif self.strategy == CompactionStrategy.SUMMARIZE:
            compacted = self._summarize(processed_messages)
        elif self.strategy == CompactionStrategy.SMART:
            compacted = self._smart_compact(processed_messages)
        elif self.strategy == CompactionStrategy.PRUNE:
            compacted = self._prune(processed_messages)
        elif self.strategy == CompactionStrategy.LLM_SUMMARIZE:
            if self.llm_summarize_fn:
                # For sync calls with LLM function, we need to run async
                try:
                    # Check if we're already in an async context
                    try:
                        loop = asyncio.get_running_loop()
                        # If in async context, fallback to naive summarization
                        compacted = self._summarize(processed_messages)
                    except RuntimeError:
                        # No running loop, safe to create one
                        compacted = asyncio.run(self._llm_summarize_async(processed_messages, focus_topic))
                except Exception:
                    # Fallback to naive summarization if async fails
                    compacted = self._summarize(processed_messages)
            else:
                compacted = self._llm_summarize(processed_messages, focus_topic)
        else:
            compacted = self._truncate(processed_messages)
        
        compacted_tokens = self.count_total_tokens(compacted)
        
        result = CompactionResult(
            original_tokens=original_tokens,
            compacted_tokens=compacted_tokens,
            messages_removed=len(messages) - len(compacted),
            messages_kept=len(compacted),
            strategy_used=self.strategy,
            tool_results_pruned=tool_results_pruned,
            previous_summary_reused=getattr(self, '_used_previous_summary', False),
            summary=self._extract_summary_text(compacted),
        )
        result.calculate_savings_pct()
        
        # Update anti-thrashing tracking based on actual results
        self._record_savings_outcome(result.savings_pct, original_tokens)
        
        return compacted, result

    async def compact_async(
        self,
        messages: List[Dict[str, Any]],
        focus_topic: str = ""
    ) -> tuple[List[Dict[str, Any]], CompactionResult]:
        """
        Compact messages to fit within token limit (asynchronous version).
        
        Args:
            messages: List of messages to compact
            focus_topic: Optional topic to focus on during summarization
            
        Returns:
            Tuple of (compacted messages, result)
        """
        # Reset state for this compaction call
        self._used_previous_summary = False
        
        original_tokens = self.count_total_tokens(messages)
        
        if original_tokens <= self.max_tokens:
            result = CompactionResult(
                original_tokens=original_tokens,
                compacted_tokens=original_tokens,
                messages_removed=0,
                messages_kept=len(messages),
                strategy_used=self.strategy
            )
            result.calculate_savings_pct()
            return messages, result

        # Anti-thrashing: if prior passes yielded too little savings, skip and
        # surface it on the result so callers can detect the skip. Without this
        # the documented ``was_skipped_due_to_low_savings`` flag never fired.
        if self._should_skip_low_savings(original_tokens):
            result = CompactionResult(
                original_tokens=original_tokens,
                compacted_tokens=original_tokens,
                messages_removed=0,
                messages_kept=len(messages),
                strategy_used=self.strategy,
                was_skipped_due_to_low_savings=True,
            )
            result.calculate_savings_pct()
            return messages, result

        # Apply tool result deduplication pre-pass if enabled
        processed_messages = messages
        tool_results_pruned = 0
        if self.config.tool_prune_before_summarise and self.tool_pruner:
            processed_messages, tool_results_pruned = self.tool_pruner.prune(
                messages, 
                self.config.max_tool_result_size
            )
        
        if self.strategy == CompactionStrategy.TRUNCATE:
            compacted = self._truncate(processed_messages)
        elif self.strategy == CompactionStrategy.SLIDING:
            compacted = self._sliding_window(processed_messages)
        elif self.strategy == CompactionStrategy.SUMMARIZE:
            compacted = self._summarize(processed_messages)
        elif self.strategy == CompactionStrategy.SMART:
            compacted = self._smart_compact(processed_messages)
        elif self.strategy == CompactionStrategy.PRUNE:
            compacted = self._prune(processed_messages)
        elif self.strategy == CompactionStrategy.LLM_SUMMARIZE:
            compacted = await self._llm_summarize_async(processed_messages, focus_topic)
        else:
            compacted = self._truncate(processed_messages)
        
        compacted_tokens = self.count_total_tokens(compacted)
        
        result = CompactionResult(
            original_tokens=original_tokens,
            compacted_tokens=compacted_tokens,
            messages_removed=len(messages) - len(compacted),
            messages_kept=len(compacted),
            strategy_used=self.strategy,
            tool_results_pruned=tool_results_pruned,
            previous_summary_reused=getattr(self, '_used_previous_summary', False),
            summary=self._extract_summary_text(compacted),
        )
        result.calculate_savings_pct()
        
        # Update anti-thrashing tracking based on actual results
        self._record_savings_outcome(result.savings_pct, original_tokens)
        
        return compacted, result

    def _extract_summary_text(self, compacted: List[Dict[str, Any]]) -> str:
        """Surface the summary text produced by summarizing strategies.

        ``CompactionResult.summary`` was historically left at ``""``, so the
        distilled summary was only reachable as an in-list system message and
        never propagated to hooks or the durable session checkpoint. This
        returns the summary the strategy just injected (LLM or naive), so
        callers/persisters (e.g. ``_persist_compaction_checkpoint``) can make
        it durable. Returns ``""`` for non-summarizing strategies.

        Only summaries produced by the *current* pass are surfaced: we read the
        message the strategy just injected into ``compacted``. We deliberately
        do NOT fall back to the instance-level ``_previous_summary``, because a
        reused compactor would then leak a stale LLM summary into a later
        TRUNCATE/SLIDING/PRUNE pass and persist an outdated checkpoint that
        drops intervening turns on resume (Issue #3062 review).
        """
        # Summarizing strategies tag their injected message with ``_compacted``.
        for msg in reversed(compacted):
            if msg.get("_compacted") and isinstance(msg.get("content"), str):
                return msg["content"]
        # Naive ``_summarize`` injects an untagged system summary line.
        for msg in reversed(compacted):
            content = msg.get("content")
            if (
                msg.get("role") == "system"
                and isinstance(content, str)
                and content.startswith("[Previous conversation summary]")
            ):
                return content
        return ""

    def _prune_tool_results(self, messages: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], int]:
        """
        Delegate tool result pruning to injected protocol implementation.
        
        If no tool pruner is provided, returns messages unchanged.
        This maintains backward compatibility while enforcing protocol-driven design.
        
        Returns:
            Tuple of (processed messages, number of tool results pruned)
        """
        if self.tool_pruner:
            return self.tool_pruner.prune(messages, self.config.max_tool_result_size)
        return messages, 0
    
    def _snap_to_pair_boundary(
        self,
        messages: List[Dict[str, Any]],
        cut_index: int,
    ) -> int:
        """Move ``cut_index`` so it never splits an assistant ``tool_calls``
        message from its matching ``tool`` result.

        ``messages[:cut_index]`` is the older segment that gets dropped or
        summarised; ``messages[cut_index:]`` is the recent segment that is
        kept verbatim. If the boundary would leave a ``tool`` result at the
        head of the kept segment whose originating assistant ``tool_calls``
        message sits in the older segment (or vice versa), strict providers
        reject the transcript with a 400. This snaps the boundary *outward*
        (to a lower index) so the whole pair is kept together on the recent
        side, which is the safe direction for the provider contract.

        Returns a boundary index in ``[0, len(messages)]``.
        """
        if cut_index <= 0 or cut_index >= len(messages):
            return max(0, min(cut_index, len(messages)))

        # Collect the tool_call ids produced by assistant messages that fall
        # in the older (dropped/summarised) segment. Any tool result in the
        # kept segment referencing one of these would be orphaned.
        def _call_ids(msg: Dict[str, Any]) -> set:
            ids = set()
            for tc in (msg.get("tool_calls") or []):
                if isinstance(tc, dict) and tc.get("id"):
                    ids.add(tc["id"])
            return ids

        # Walk the boundary outward while the first kept message is an orphaned
        # tool result, i.e. its tool_call_id was emitted before the cut.
        older_call_ids = set()
        for msg in messages[:cut_index]:
            older_call_ids |= _call_ids(msg)

        while cut_index > 0:
            head = messages[cut_index]
            head_response_id = head.get("tool_call_id")
            if head.get("role") == "tool" and head_response_id in older_call_ids:
                # Pull the boundary back to include the preceding message; keep
                # going until the emitting assistant tool_calls message is on
                # the kept side too.
                cut_index -= 1
                older_call_ids -= _call_ids(messages[cut_index])
            else:
                break

        return cut_index

    def preview_older_slice(
        self, messages: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Return the non-system prefix that compaction may discard.

        The recent-count boundary (``preserve_recent``) is the *minimum* region
        every strategy drops. Budget-driven strategies (SLIDING, and TRUNCATE's
        second pass) can drop **more** older messages to reach ``target_tokens``.
        To ensure a pre-compaction consumer is offered every message that could
        be discarded — so durable facts are never silently lost — this returns a
        safe *superset*: whichever boundary (count- or token-budget-based) covers
        the larger older region, with tool-call pairs kept intact. It never
        mutates the transcript.
        """
        other_messages = [
            message
            for message in messages
            if not (self.preserve_system and message.get("role") == "system")
        ]
        count_cut = max(0, len(other_messages) - self.preserve_recent)

        # TRUNCATE and sliding strategies can discard additional messages to
        # satisfy the token budget. Simulate their pure list transforms so the
        # preview uses the same second-pass tool-pair behavior as compaction.
        if self.strategy == CompactionStrategy.TRUNCATE:
            compacted = self._truncate(messages)
        elif self.strategy in {CompactionStrategy.SLIDING, CompactionStrategy.SMART}:
            compacted = self._sliding_window(messages)
        else:
            compacted = None
        if compacted is not None:
            kept_ids = {id(message) for message in compacted}
            strategy_cut = next(
                (
                    index
                    for index, message in enumerate(other_messages)
                    if id(message) in kept_ids
                ),
                len(other_messages),
            )
            return list(other_messages[:strategy_cut])

        # Token-budget boundary: mirror the sliding window's kept-from-the-end
        # accounting (system messages count toward the budget) so we also cover
        # older messages that budget-constrained truncation would drop.
        system_tokens = (
            self.count_total_tokens(
                [m for m in messages if m.get("role") == "system"]
            )
            if self.preserve_system
            else 0
        )
        budget_kept = 0
        running = system_tokens
        for message in reversed(other_messages):
            running += self.count_message_tokens(message)
            if running <= self.target_tokens:
                budget_kept += 1
            else:
                break
        budget_cut = len(other_messages) - budget_kept

        # For summarization/pruning, the count boundary is the destructive
        # region. Keep the budget boundary as a conservative fallback for
        # custom strategies using this compactor.
        cut = self._snap_to_pair_boundary(
            other_messages, max(count_cut, budget_cut)
        )
        return list(other_messages[:cut])

    def _truncate(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Truncate oldest messages."""
        result = []
        
        # Separate system and non-system messages
        system_msgs = []
        other_msgs = []
        
        for msg in messages:
            if self.preserve_system and msg.get("role") == "system":
                system_msgs.append(msg)
            else:
                other_msgs.append(msg)
        
        # Always keep system messages
        result.extend(system_msgs)
        
        # Keep recent messages. Snap the boundary outward so a tool result at
        # the head of the kept window is never orphaned from its assistant
        # tool_calls message (strict providers 400 on an orphaned tool result).
        if other_msgs and len(other_msgs) > self.preserve_recent:
            cut = self._snap_to_pair_boundary(
                other_msgs, len(other_msgs) - self.preserve_recent
            )
        else:
            cut = 0
        recent = other_msgs[cut:]
        
        # Add recent messages
        result.extend(recent)
        
        # If still over limit, truncate more. Drop the whole leading tool pair
        # together (an assistant tool_calls message plus its tool results) so we
        # never leave an orphaned tool result at the head of the kept window.
        while self.count_total_tokens(result) > self.target_tokens and len(result) > 1:
            # Find the oldest droppable (non-system when preserved) message.
            start = None
            for i, msg in enumerate(result):
                if not (self.preserve_system and msg.get("role") == "system"):
                    start = i
                    break
            if start is None:
                # Only system messages remain but still over budget — stop to avoid infinite loop
                break

            # If the oldest droppable message emits tool_calls, drop it together
            # with all of its immediately-following tool results.
            drop_ids = set()
            for tc in (result[start].get("tool_calls") or []):
                if isinstance(tc, dict) and tc.get("id"):
                    drop_ids.add(tc["id"])
            end = start + 1
            while (
                drop_ids
                and end < len(result)
                and result[end].get("role") == "tool"
                and result[end].get("tool_call_id") in drop_ids
            ):
                end += 1
            del result[start:end]
        
        return result
    
    def _sliding_window(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Keep a sliding window of recent messages."""
        result = []
        
        # Keep system messages
        for msg in messages:
            if self.preserve_system and msg.get("role") == "system":
                result.append(msg)
        
        # Add messages from end until we hit target. Track the boundary index
        # into non_system so we can snap it to keep tool pairs together.
        non_system = [m for m in messages if m.get("role") != "system"]
        
        kept = 0
        window: List[Dict[str, Any]] = []
        for msg in reversed(non_system):
            if self.count_total_tokens(result + [msg] + window) <= self.target_tokens:
                window.insert(0, msg)
                kept += 1
            else:
                break
        
        # Snap the boundary outward so a tool result kept at the window head is
        # not orphaned from its assistant tool_calls left outside the window.
        cut = self._snap_to_pair_boundary(non_system, len(non_system) - kept)
        window = non_system[cut:]
        
        return result + window
    
    def _summarize(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Summarize old messages (simplified version)."""
        result = []
        
        # Keep system messages
        system_msgs = [m for m in messages if m.get("role") == "system"]
        other_msgs = [m for m in messages if m.get("role") != "system"]
        
        result.extend(system_msgs)
        
        # Choose the recent/older boundary by count, then snap it so a
        # tool_calls message and its result are never split across it.
        if len(other_msgs) > self.preserve_recent:
            cut = self._snap_to_pair_boundary(
                other_msgs, len(other_msgs) - self.preserve_recent
            )
        else:
            cut = 0
        recent = other_msgs[cut:]
        older = other_msgs[:cut]
        
        if older:
            # Create a simple summary
            summary_parts = []
            for msg in older:
                role = msg.get("role", "unknown")
                content = msg.get("content", "")
                if isinstance(content, str) and content:
                    # Take first 100 chars
                    summary_parts.append(f"{role}: {content[:100]}...")
            
            if summary_parts:
                summary = "[Previous conversation summary]\n" + "\n".join(summary_parts[:5])
                result.append({
                    "role": "system",
                    "content": summary
                })
        
        result.extend(recent)
        
        return result
    
    def _smart_compact(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Smart compaction based on message importance."""
        # For now, use sliding window as base
        return self._sliding_window(messages)
    
    def _prune(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Prune old tool outputs while keeping tool calls.
        
        This reduces token usage by removing verbose tool outputs
        from older messages while preserving the context of what
        tools were called.
        """
        result = []
        
        # Separate system and other messages
        system_msgs = [m for m in messages if m.get("role") == "system"]
        other_msgs = [m for m in messages if m.get("role") != "system"]
        
        result.extend(system_msgs)
        
        # Keep recent messages intact. Snap the boundary so a tool_calls
        # message and its result are pruned/kept together (prune only rewrites
        # tool-result *content*, but a snapped boundary keeps intent consistent).
        if len(other_msgs) > self.preserve_recent:
            cut = self._snap_to_pair_boundary(
                other_msgs, len(other_msgs) - self.preserve_recent
            )
        else:
            cut = 0
        recent = other_msgs[cut:]
        older = other_msgs[:cut]
        
        # Prune older messages
        for msg in older:
            role = msg.get("role", "")
            content = msg.get("content", "")
            
            # If this is a tool result, truncate it (use smart format)
            if role == "tool" or msg.get("tool_call_id"):
                if isinstance(content, str) and len(content) > 500:
                    pruned_msg = msg.copy()
                    tail_size = min(100, len(content) // 5)
                    head = content[:200]
                    tail = content[-tail_size:] if tail_size > 0 else ""
                    pruned_msg["content"] = f"{head}\n...[{len(content):,} chars, showing first/last portions]...\n{tail}"
                    result.append(pruned_msg)
                else:
                    result.append(msg)
            else:
                result.append(msg)
        
        result.extend(recent)
        return result
    
    def clear_tool_results(
        self,
        messages: List[Dict[str, Any]],
        *,
        keep_recent: int = 6,
        placeholder: str = "[tool result cleared to save context; re-fetch if needed]"
    ) -> List[Dict[str, Any]]:
        """
        Clear old, re-fetchable tool result contents while keeping tool_calls intact.

        Replaces the content of older ``tool`` messages with a short placeholder
        so the model still knows the call happened (and with what args, via the
        assistant ``tool_calls``), but the verbose output no longer consumes the
        window. The most recent ``keep_recent`` tool results are preserved.

        Args:
            messages: Conversation messages
            keep_recent: Number of most recent tool results to keep verbatim
            placeholder: Replacement content for cleared tool results

        Returns:
            New message list with old tool results cleared
        """
        tool_idxs = [i for i, m in enumerate(messages) if m.get("role") == "tool"]
        to_clear = set(tool_idxs[:-keep_recent]) if len(tool_idxs) > keep_recent else set()

        out = []
        for i, m in enumerate(messages):
            if (
                i in to_clear
                and isinstance(m.get("content"), str)
                and m["content"] != placeholder
            ):
                m = {**m, "content": placeholder}
            out.append(m)
        return out

    def _llm_summarize(self, messages: List[Dict[str, Any]], focus_topic: str = "") -> List[Dict[str, Any]]:
        """
        Use LLM to summarize older messages with iterative support.
        
        Supports iterative summarization - if we have a previous summary,
        we only summarize the new messages since that summary.
        Also includes anti-injection framing when configured.
        
        Args:
            messages: List of messages to compact
            focus_topic: Optional topic to focus on during summarization
        """
        self._used_previous_summary = False
        result = []
        summary_written = False
        
        # Keep system messages
        system_msgs = [m for m in messages if m.get("role") == "system"]
        other_msgs = [m for m in messages if m.get("role") != "system"]
        
        result.extend(system_msgs)
        
        # Keep recent messages, snapping the boundary so tool_calls/result
        # pairs are never split across the recent/older divide.
        if len(other_msgs) > self.preserve_recent:
            recent_cut = self._snap_to_pair_boundary(
                other_msgs, len(other_msgs) - self.preserve_recent
            )
        else:
            recent_cut = 0
        recent = other_msgs[recent_cut:]
        
        # Determine what to summarize
        total_original_messages = len(messages)
        if (self.config.enable_iterative_summary and 
            self._previous_summary and 
            total_original_messages > self._previous_summary_global_idx):
            # Iterative: summarize only new messages since previous summary
            # Calculate how many old messages to summarize based on global position
            messages_since_summary = total_original_messages - self._previous_summary_global_idx
            new_older_messages = max(0, messages_since_summary - self.preserve_recent)
            if new_older_messages > 0:
                to_summarize = other_msgs[-messages_since_summary:recent_cut]
            else:
                to_summarize = []
            self._used_previous_summary = True
        else:
            # Fresh summary: summarize all older messages (kept in sync with the
            # snapped recent boundary so a tool pair is never split)
            to_summarize = other_msgs[:recent_cut]
            self._used_previous_summary = False
        
        if to_summarize or self._previous_summary:
            # Build summary content
            summary_parts = []
            
            # Include previous summary if doing iterative summarization
            if self._used_previous_summary and self._previous_summary:
                summary_parts.append(f"[Previous Summary]: {self._previous_summary}")
                summary_parts.append("[New Activity]:")
            
            # Add new messages to summarize
            for msg in to_summarize:
                role = msg.get("role", "unknown")
                content = msg.get("content", "")
                if isinstance(content, str) and content:
                    # Extract key information with focus consideration
                    if focus_topic and focus_topic.lower() in content.lower():
                        # Prioritize content related to focus topic
                        summary_parts.append(f"[{role}] *FOCUS*: {content[:200]}...")
                    else:
                        summary_parts.append(f"[{role}]: {content[:150]}...")
            
            if summary_parts:
                focus_hint = f"\nFocus on: {focus_topic}" if focus_topic else ""
                
                if self._used_previous_summary:
                    summary = (
                        f"[Iterative conversation summary - update with new activity{focus_hint}]\n"
                        + "\n".join(summary_parts[:15])
                    )
                else:
                    summary = (
                        f"[Compacted conversation history - summarize key points{focus_hint}]\n"
                        + "\n".join(summary_parts[:10])
                    )
                
                # Apply anti-injection prefix if configured
                if hasattr(self.config, 'compaction_prefix') and self.config.compaction_prefix:
                    summary = f"{self.config.compaction_prefix}\n\n{summary}"
                
                summary_msg = {
                    "role": "system",
                    "content": summary,
                    "_compacted": True,
                    "_original_count": len(to_summarize),
                    "_iterative": self._used_previous_summary,
                    "_focus_topic": focus_topic
                }
                result.append(summary_msg)
                
                # Remember the summary text for the next iterative pass. The
                # global baseline is set below against the *returned* list length
                # (see the note there) — not len(messages) — so the next call's
                # `messages_since_summary` counts only genuinely new turns.
                self._previous_summary = summary
                summary_written = True
        
        result.extend(recent)
        if summary_written:
            # Baseline for the NEXT iterative pass must be the length of the
            # compacted list we actually return (system + summary + recent),
            # NOT len(messages) of the pre-compaction input. Using the input
            # length made the iterative branch compare two differently-based
            # lengths, so later passes sliced the wrong window and silently
            # dropped intervening conversation turns.
            self._previous_summary_global_idx = len(result)
        return result

    async def _llm_summarize_async(self, messages: List[Dict[str, Any]], focus_topic: str = "") -> List[Dict[str, Any]]:
        """
        Use LLM to intelligently summarize older messages.
        
        This method invokes the agent's LLM to create a meaningful summary
        that preserves key facts, identifiers, and the user's intent.
        
        Args:
            messages: List of messages to compact
            focus_topic: Optional topic to focus on during summarization
        """
        self._used_previous_summary = False
        result = []
        summary_written = False
        
        # Keep system messages
        system_msgs = [m for m in messages if m.get("role") == "system"]
        other_msgs = [m for m in messages if m.get("role") != "system"]
        
        result.extend(system_msgs)
        
        # Keep recent messages, snapping the boundary so tool_calls/result
        # pairs are never split across the recent/older divide.
        if len(other_msgs) > self.preserve_recent:
            recent_cut = self._snap_to_pair_boundary(
                other_msgs, len(other_msgs) - self.preserve_recent
            )
        else:
            recent_cut = 0
        recent = other_msgs[recent_cut:]
        
        # Determine what to summarize based on iterative settings
        total_original_messages = len(messages)
        if (self.config.enable_iterative_summary and 
            self._previous_summary and 
            total_original_messages > self._previous_summary_global_idx):
            # Iterative: summarize only new messages since previous summary
            messages_since_summary = total_original_messages - self._previous_summary_global_idx
            new_older_messages = max(0, messages_since_summary - self.preserve_recent)
            if new_older_messages > 0:
                older = other_msgs[-messages_since_summary:recent_cut]
            else:
                older = []
            self._used_previous_summary = True
        else:
            # Fresh summary: summarize all older messages (kept in sync with the
            # snapped recent boundary so a tool pair is never split)
            older = other_msgs[:recent_cut]
            self._used_previous_summary = False
        
        if older and self.llm_summarize_fn:
            try:
                # Format messages for summarization using protocol
                if self.message_formatter:
                    history_text = self.message_formatter.format_for_summary(older)
                else:
                    # Fallback to basic formatting if no protocol implementation
                    history_text = str(older)
                
                # Create summarization prompt that preserves important information
                focus_hint = f" Focus especially on: {focus_topic}." if focus_topic else ""
                iterative_hint = ""
                if self._used_previous_summary and self._previous_summary:
                    iterative_hint = f"\n\n[Previous Summary]: {self._previous_summary}\n[New Activity to Add]:"
                
                prompt = (
                    "Summarise the following conversation history. Preserve verbatim: "
                    "all file paths, IDs, hashes, URLs, task references, error messages, "
                    "tool outputs, and the user's requests. Be concise but complete. "
                    f"Focus on facts and actions taken, not general conversation.{focus_hint}"
                    f"{iterative_hint}\n\n{history_text}"
                )
                
                # Call the LLM for summarization
                summary = await self.llm_summarize_fn(prompt)
                
                # Add the LLM-generated summary as a system message
                summary_content = summary
                if self._used_previous_summary:
                    summary_content = f"[Iterative conversation summary]\n{summary}"
                else:
                    summary_content = f"[Previous conversation summary]\n{summary}"
                
                result.append({
                    "role": "system",
                    "content": summary_content,
                    "_compacted": True,
                    "_original_count": len(older),
                    "_llm_generated": True,
                    "_iterative": self._used_previous_summary,
                    "_focus_topic": focus_topic
                })
                
                # Remember the summary text for the next iterative pass. The
                # global baseline is set against the *returned* list length
                # below (not len(messages)) so later passes count only new turns
                # and never drop intervening conversation from the result.
                self._previous_summary = summary
                summary_written = True
            except Exception as e:
                # Fallback to naive summarization if LLM call fails
                import logging
                logging.warning(f"LLM summarization failed, falling back to naive: {e}")
                summary_parts = []
                for msg in older:
                    role = msg.get("role", "unknown")
                    content = str(msg.get("content", ""))
                    if content:
                        # Extract key information
                        summary_parts.append(f"[{role}]: {content[:150]}...")
                
                if summary_parts:
                    summary = (
                        "[Compacted conversation history - LLM summarization failed]\n"
                        + "\n".join(summary_parts[:10])
                    )
                    result.append({
                        "role": "system",
                        "content": summary,
                        "_compacted": True,
                        "_original_count": len(older),
                        "_fallback": True,
                    })
        elif older:
            # Fallback to naive summarization if no LLM function
            summary_parts = []
            for msg in older:
                role = msg.get("role", "unknown")
                content = str(msg.get("content", ""))
                if content:
                    summary_parts.append(f"[{role}]: {content[:150]}...")
            
            if summary_parts:
                summary = (
                    "[Compacted conversation history - no LLM function]\n"
                    + "\n".join(summary_parts[:10])
                )
                result.append({
                    "role": "system",
                    "content": summary,
                    "_compacted": True,
                    "_original_count": len(older),
                    "_fallback": True,
                })
        
        result.extend(recent)
        if summary_written:
            # Baseline for the NEXT iterative pass is the length of the
            # compacted list we return, not len(messages) of the input, so
            # subsequent passes summarize (not silently drop) new turns.
            self._previous_summary_global_idx = len(result)
        return result

    def _format_messages_for_summary(self, messages: List[Dict[str, Any]]) -> str:
        """
        Delegate message formatting to protocol implementation.
        
        If no formatter is provided, returns basic string representation.
        """
        if self.message_formatter:
            return self.message_formatter.format_for_summary(messages)
        return str(messages)
    
    def _build_structured_summary(self, messages: List[Dict[str, Any]]) -> str:
        """
        Delegate structured summary building to protocol implementation.
        
        If no summary builder is provided, returns basic summary.
        """
        if self.summary_builder:
            return self.summary_builder.build_structured_summary(messages)
        return f"Summary of {len(messages)} messages"
    
    def _merge_summaries(self, previous: str, current: str) -> str:
        """
        Delegate summary merging to protocol implementation.
        
        If no summary builder is provided, returns current summary only.
        """
        if self.summary_builder:
            return self.summary_builder.merge_summaries(previous, current)
        return current
    
    def get_stats(self, messages: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Get statistics about messages."""
        total_tokens = self.count_total_tokens(messages)
        
        return {
            "message_count": len(messages),
            "total_tokens": total_tokens,
            "max_tokens": self.max_tokens,
            "target_tokens": self.target_tokens,
            "needs_compaction": total_tokens > self.max_tokens,
            "utilization": total_tokens / self.max_tokens if self.max_tokens > 0 else 0,
            "compaction_config": {
                "anti_injection_enabled": bool(self.config.compaction_prefix),
                "structured_template": self.config.structured_template,
                "iterative_update": self.config.iterative_update,
                "has_previous_summary": self._previous_summary is not None
            }
        }
