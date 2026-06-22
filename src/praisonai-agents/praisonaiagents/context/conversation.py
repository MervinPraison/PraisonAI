"""
Conversation Compaction Implementations for PraisonAI Agents.

Provides intelligent conversation analysis and compaction that preserves
conversation continuity through structured summarization.

Implementation follows AGENTS.md protocol-driven design:
- Protocols in core SDK (protocols.py)
- Implementations in this module (lazy loaded)
- Configurable strategies with sensible defaults
"""

import re
import hashlib
import logging
from typing import Dict, List, Any, Optional, Tuple, Set
from dataclasses import dataclass

from .protocols import ConversationAnalyzerProtocol, ConversationCompactorProtocol, ConversationContext
from .tokens import estimate_messages_tokens, estimate_message_tokens


class HybridConversationAnalyzer:
    """
    Hybrid conversation analyzer using both LLM and rule-based analysis.
    
    Uses LLM for deep understanding when available, falls back to
    rule-based analysis for reliability and performance.
    """
    
    def __init__(self, llm_analyze_fn: Optional[callable] = None, fallback_strategy: str = "rule_based"):
        """
        Initialize hybrid analyzer.
        
        Args:
            llm_analyze_fn: Optional LLM function(messages, task) -> str for analysis
            fallback_strategy: Strategy when LLM unavailable ("rule_based" or "keyword")
        """
        self.llm_analyze_fn = llm_analyze_fn
        self.fallback_strategy = fallback_strategy
    
    def analyze_conversation(self, messages: List[Dict[str, Any]]) -> ConversationContext:
        """Analyze conversation using hybrid approach."""
        if self.llm_analyze_fn:
            try:
                return self._llm_analysis(messages)
            except Exception as e:
                # Fall back to rule-based analysis
                logging.debug(f"LLM analysis failed, falling back to rule-based analysis: {e}")
        
        return self._rule_based_analysis(messages)
    
    def extract_key_decisions(self, messages: List[Dict[str, Any]]) -> List[str]:
        """Extract key decisions from conversation."""
        decisions = []
        
        # Decision indicators
        decision_patterns = [
            r"(?i)(decided|choosing|selected|picked|going with|settled on) (.+)",
            r"(?i)(let's|we should|i'll|will) (.+)",
            r"(?i)(agreed to|approved|confirmed) (.+)",
            r"(?i)(final decision|conclusion) (.+)",
        ]
        
        for msg in messages:
            content = str(msg.get("content", ""))
            if not content or msg.get("role") not in ("user", "assistant"):
                continue
            
            for pattern in decision_patterns:
                matches = re.finditer(pattern, content)
                for match in matches:
                    decision = match.group(2).strip()
                    if len(decision) > 10 and len(decision) < 200:  # Reasonable length
                        decisions.append(decision)
        
        # Remove duplicates while preserving order
        seen = set()
        unique_decisions = []
        for decision in decisions:
            normalized = decision.lower().strip()
            if normalized not in seen:
                seen.add(normalized)
                unique_decisions.append(decision)
        
        return unique_decisions[-10:]  # Keep last 10 decisions
    
    def identify_main_topic(self, messages: List[Dict[str, Any]]) -> str:
        """Identify main topic using frequency analysis."""
        if not messages:
            return "General conversation"
        
        # Collect text content
        text_content = []
        for msg in messages:
            content = str(msg.get("content", ""))
            if content and msg.get("role") in ("user", "assistant"):
                text_content.append(content.lower())
        
        if not text_content:
            return "General conversation"
        
        # Extract potential topics (nouns and noun phrases)
        topic_candidates = set()
        combined_text = " ".join(text_content)
        
        # Simple topic extraction patterns
        topic_patterns = [
            r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\b",  # Capitalized phrases
            r"\b(implement|build|create|develop|design)\s+([a-z\s]+)",  # Action + object
            r"\b(working on|focusing on|dealing with)\s+([a-z\s]+)",  # Focus indicators
        ]
        
        for pattern in topic_patterns:
            matches = re.finditer(pattern, combined_text, re.IGNORECASE)
            for match in matches:
                candidate = match.group(1 if len(match.groups()) == 1 else 2).strip()
                if 3 <= len(candidate) <= 50:  # Reasonable length
                    topic_candidates.add(candidate)
        
        if topic_candidates:
            # Return most frequently mentioned candidate
            word_freq = {}
            for candidate in topic_candidates:
                freq = combined_text.count(candidate.lower())
                if freq > 1:  # Mentioned more than once
                    word_freq[candidate] = freq
            
            if word_freq:
                return max(word_freq.keys(), key=word_freq.get)
        
        # Fallback: Look at first user message
        for msg in messages:
            if msg.get("role") == "user":
                content = str(msg.get("content", ""))
                if content:
                    # Extract first sentence or first 100 chars
                    first_sentence = content.split('.')[0].strip()
                    if len(first_sentence) < 100:
                        return first_sentence
                    return content[:100] + "..." if len(content) > 100 else content
        
        return "General conversation"
    
    def summarize_progress(self, messages: List[Dict[str, Any]]) -> str:
        """Summarize progress made in conversation."""
        progress_indicators = []
        
        # Progress patterns
        progress_patterns = [
            r"(?i)(completed|finished|done|implemented|created) (.+)",
            r"(?i)(successfully|working|progress on) (.+)",
            r"(?i)(next step|now|then) (.+)",
            r"(?i)(achieved|accomplished|solved) (.+)",
        ]
        
        for msg in messages:
            content = str(msg.get("content", ""))
            role = msg.get("role", "")
            
            if not content or role not in ("user", "assistant"):
                continue
            
            for pattern in progress_patterns:
                matches = re.finditer(pattern, content)
                for match in matches:
                    progress = match.group(2).strip()
                    if 5 <= len(progress) <= 150:  # Reasonable length
                        progress_indicators.append(progress)
        
        if progress_indicators:
            # Summarize last few progress items
            recent_progress = progress_indicators[-5:]
            return "; ".join(recent_progress)
        
        # Fallback: Count message exchanges as progress indicator
        message_count = len([m for m in messages if m.get("role") in ("user", "assistant")])
        if message_count > 5:
            return f"Active conversation with {message_count} exchanges"
        
        return "Initial discussion phase"
    
    def _llm_analysis(self, messages: List[Dict[str, Any]]) -> ConversationContext:
        """Use LLM for deep conversation analysis."""
        try:
            # Prepare conversation text for analysis
            conversation_text = self._prepare_conversation_text(messages)
            
            # LLM analysis prompt
            analysis_prompt = """
            Analyze this conversation and extract key information in JSON format:
            
            {
                "main_topic": "brief description of main topic",
                "current_goal": "what the user is trying to achieve",
                "progress_summary": "progress made so far",
                "key_decisions": ["decision1", "decision2"],
                "important_facts": ["fact1", "fact2"],
                "action_items": ["item1", "item2"],
                "user_preferences": ["pref1", "pref2"],
                "conversation_tone": "professional|casual|technical|friendly"
            }
            
            Conversation:
            """ + conversation_text
            
            # Call LLM
            response = self.llm_analyze_fn(analysis_prompt, max_tokens=800)
            
            # Parse JSON response
            import json
            try:
                analysis = json.loads(response.strip())
                
                return ConversationContext(
                    main_topic=analysis.get("main_topic", ""),
                    current_goal=analysis.get("current_goal", ""),
                    progress_summary=analysis.get("progress_summary", ""),
                    key_decisions=analysis.get("key_decisions", []),
                    important_facts=analysis.get("important_facts", []),
                    action_items=analysis.get("action_items", []),
                    user_preferences=analysis.get("user_preferences", []),
                    conversation_tone=analysis.get("conversation_tone", "professional"),
                    original_message_count=len(messages),
                )
            except json.JSONDecodeError as e:
                # Fall back to rule-based if JSON parsing fails
                logging.debug(f"Failed to parse LLM response as JSON: {e}, response: {response[:100]}")
        except Exception as e:
            # Fall back to rule-based analysis if LLM call fails
            logging.debug(f"LLM analysis error: {e}")
            pass
        
        # Fallback to rule-based analysis
        return self._rule_based_analysis(messages)
    
    def _rule_based_analysis(self, messages: List[Dict[str, Any]]) -> ConversationContext:
        """Rule-based conversation analysis as fallback."""
        main_topic = self.identify_main_topic(messages)
        key_decisions = self.extract_key_decisions(messages)
        progress_summary = self.summarize_progress(messages)
        
        # Extract user preferences (simple pattern matching)
        preferences = self._extract_preferences(messages)
        
        # Extract tool results summary
        tool_summaries = self._extract_tool_summaries(messages)
        
        # Extract important facts (statements from assistant)
        facts = self._extract_facts(messages)
        
        # Extract action items (future tense statements)
        action_items = self._extract_action_items(messages)
        
        # Determine conversation tone
        tone = self._determine_tone(messages)
        
        return ConversationContext(
            main_topic=main_topic,
            current_goal=self._extract_goal(messages),
            progress_summary=progress_summary,
            key_decisions=key_decisions,
            important_facts=facts,
            action_items=action_items,
            user_preferences=preferences,
            tool_results_summary=tool_summaries,
            conversation_tone=tone,
            original_message_count=len(messages),
        )
    
    def _prepare_conversation_text(self, messages: List[Dict[str, Any]]) -> str:
        """Prepare conversation text for LLM analysis."""
        text_parts = []
        for msg in messages:
            role = msg.get("role", "")
            content = str(msg.get("content", ""))
            
            if content and role in ("user", "assistant"):
                # Truncate very long content
                if len(content) > 1000:
                    content = content[:900] + "...[truncated]"
                text_parts.append(f"{role.upper()}: {content}")
        
        return "\n\n".join(text_parts[-20:])  # Last 20 messages
    
    def _extract_preferences(self, messages: List[Dict[str, Any]]) -> List[str]:
        """Extract user preferences."""
        preferences = []
        preference_patterns = [
            r"(?i)(prefer|like|want|need) (.+)",
            r"(?i)(don't want|avoid|dislike) (.+)",
            r"(?i)(always|never|usually) (.+)",
        ]
        
        for msg in messages:
            if msg.get("role") == "user":
                content = str(msg.get("content", ""))
                for pattern in preference_patterns:
                    matches = re.finditer(pattern, content)
                    for match in matches:
                        pref = match.group(2).strip()
                        if 5 <= len(pref) <= 100:
                            preferences.append(pref)
        
        return list(dict.fromkeys(preferences))[-5:]  # Last 5 unique preferences
    
    def _extract_tool_summaries(self, messages: List[Dict[str, Any]]) -> List[str]:
        """Extract summaries of tool results."""
        summaries = []
        
        for msg in messages:
            if msg.get("role") == "tool":
                tool_name = msg.get("name", "Unknown tool")
                content = str(msg.get("content", ""))
                
                if content:
                    # Create brief summary
                    summary = f"{tool_name}: "
                    if len(content) > 200:
                        summary += content[:150] + "..."
                    else:
                        summary += content
                    summaries.append(summary)
        
        return summaries[-5:]  # Last 5 tool results
    
    def _extract_facts(self, messages: List[Dict[str, Any]]) -> List[str]:
        """Extract important factual statements."""
        facts = []
        fact_patterns = [
            r"(?i)(it is|this is|that is) (.+)",
            r"(?i)(the result is|outcome is|answer is) (.+)",
            r"(?i)(according to|based on) (.+)",
        ]
        
        for msg in messages:
            if msg.get("role") == "assistant":
                content = str(msg.get("content", ""))
                for pattern in fact_patterns:
                    matches = re.finditer(pattern, content)
                    for match in matches:
                        fact = match.group(2).strip()
                        if 10 <= len(fact) <= 200:
                            facts.append(fact)
        
        return list(dict.fromkeys(facts))[-5:]  # Last 5 unique facts
    
    def _extract_action_items(self, messages: List[Dict[str, Any]]) -> List[str]:
        """Extract action items and next steps."""
        actions = []
        action_patterns = [
            r"(?i)(need to|should|will|going to) (.+)",
            r"(?i)(next step|todo|action item) (.+)",
            r"(?i)(plan to|intend to) (.+)",
        ]
        
        for msg in messages:
            content = str(msg.get("content", ""))
            for pattern in action_patterns:
                matches = re.finditer(pattern, content)
                for match in matches:
                    action = match.group(2).strip()
                    if 5 <= len(action) <= 150:
                        actions.append(action)
        
        return list(dict.fromkeys(actions))[-5:]  # Last 5 unique actions
    
    def _extract_goal(self, messages: List[Dict[str, Any]]) -> str:
        """Extract current goal from conversation."""
        goal_patterns = [
            r"(?i)(trying to|want to|need to|goal is) (.+)",
            r"(?i)(help me|can you) (.+)",
            r"(?i)(working on|building|creating) (.+)",
        ]
        
        # Look for goals in recent user messages first
        for msg in reversed(messages):
            if msg.get("role") == "user":
                content = str(msg.get("content", ""))
                for pattern in goal_patterns:
                    match = re.search(pattern, content)
                    if match:
                        goal = match.group(2).strip()
                        if 5 <= len(goal) <= 200:
                            return goal
        
        return "Continue conversation"
    
    def _determine_tone(self, messages: List[Dict[str, Any]]) -> str:
        """Determine conversation tone."""
        # Count informal vs formal indicators
        informal_count = 0
        formal_count = 0
        
        for msg in messages:
            content = str(msg.get("content", "")).lower()
            
            # Informal indicators
            informal_patterns = ["yeah", "ok", "cool", "awesome", "thanks", "lol", "btw"]
            formal_patterns = ["however", "therefore", "furthermore", "nevertheless", "regarding"]
            
            for pattern in informal_patterns:
                informal_count += content.count(pattern)
            
            for pattern in formal_patterns:
                formal_count += content.count(pattern)
        
        if informal_count > formal_count:
            return "casual"
        elif formal_count > informal_count:
            return "formal"
        else:
            return "professional"


class IntelligentConversationCompactor:
    """
    Intelligent conversation compactor that preserves continuity.
    
    Uses conversation analysis to create structured summaries that
    maintain narrative flow and critical context.
    """
    
    def __init__(
        self,
        analyzer: ConversationAnalyzerProtocol,
        llm_summarize_fn: Optional[callable] = None,
        min_compaction_ratio: float = 0.3,
        preserve_system_messages: bool = True,
    ):
        """
        Initialize conversation compactor.
        
        Args:
            analyzer: Conversation analyzer for context extraction
            llm_summarize_fn: Optional LLM function for summarization
            min_compaction_ratio: Minimum compression ratio (0.3 = 30% savings)
            preserve_system_messages: Always keep system messages
        """
        self.analyzer = analyzer
        self.llm_summarize_fn = llm_summarize_fn
        self.min_compaction_ratio = min_compaction_ratio
        self.preserve_system_messages = preserve_system_messages
    
    def compact_conversation(
        self, 
        messages: List[Dict[str, Any]], 
        target_tokens: int,
        preserve_recent: int = 5
    ) -> Tuple[List[Dict[str, Any]], ConversationContext]:
        """Compact conversation while preserving continuity."""
        original_tokens = estimate_messages_tokens(messages)
        
        if original_tokens <= target_tokens:
            # No compaction needed
            context = ConversationContext(original_message_count=len(messages))
            return messages, context
        
        # Separate message types
        system_msgs = [m for m in messages if m.get("role") == "system"]
        other_msgs = [m for m in messages if m.get("role") != "system"]
        
        # Calculate tokens used by system messages and recent messages
        system_tokens = estimate_messages_tokens(system_msgs) if self.preserve_system_messages else 0
        recent_msgs = other_msgs[-preserve_recent:] if other_msgs else []
        recent_tokens = estimate_messages_tokens(recent_msgs)
        
        # Available space for summary
        available_tokens = target_tokens - system_tokens - recent_tokens
        
        if available_tokens <= 0:
            # Emergency: truncate to fit
            if self.preserve_system_messages:
                result = system_msgs + recent_msgs[-2:]  # Keep last 2
            else:
                result = recent_msgs[-3:]  # Keep last 3
            
            context = ConversationContext(
                original_message_count=len(messages),
                compacted_message_count=len(result),
            )
            return result, context
        
        # Find messages to compact (exclude recent ones)
        compact_msgs = other_msgs[:-preserve_recent] if len(other_msgs) > preserve_recent else []
        
        if not compact_msgs:
            # Nothing to compact
            context = ConversationContext(original_message_count=len(messages))
            return messages, context
        
        # Analyze conversation to extract context
        context = self.analyzer.analyze_conversation(compact_msgs)
        context.original_message_count = len(messages)
        context.compacted_message_count = len(system_msgs) + 1 + len(recent_msgs)  # +1 for summary
        
        # Create structured summary
        summary_msg = context.to_summary_message()
        
        # Check if compaction saves enough tokens
        result = []
        if self.preserve_system_messages:
            result.extend(system_msgs)
        
        result.append(summary_msg)
        result.extend(recent_msgs)
        
        final_tokens = estimate_messages_tokens(result)
        savings_ratio = (original_tokens - final_tokens) / original_tokens
        
        if savings_ratio < self.min_compaction_ratio:
            # Not enough savings, return original
            context = ConversationContext(original_message_count=len(messages))
            return messages, context
        
        return result, context
    
    def should_compact(self, messages: List[Dict[str, Any]], threshold_tokens: int) -> bool:
        """Determine if conversation should be compacted."""
        current_tokens = estimate_messages_tokens(messages)
        return current_tokens > threshold_tokens
    
    def find_compaction_boundaries(self, messages: List[Dict[str, Any]]) -> List[Tuple[int, int]]:
        """Find natural boundaries for compaction."""
        boundaries = []
        
        # Look for topic changes, long pauses, or completed tasks
        current_start = 0
        
        for i, msg in enumerate(messages):
            content = str(msg.get("content", "")).lower()
            
            # Boundary indicators
            if any(indicator in content for indicator in [
                "let's move on", "next topic", "new question", "switching to",
                "completed", "done with", "finished", "solved"
            ]):
                if i - current_start > 3:  # Minimum segment size
                    boundaries.append((current_start, i))
                    current_start = i + 1
        
        # Add final segment if exists
        if current_start < len(messages) - 1:
            boundaries.append((current_start, len(messages) - 1))
        
        return boundaries


# Factory functions for lazy loading (following AGENTS.md protocol-driven design)

def get_conversation_analyzer(
    strategy: str = "hybrid",
    llm_analyze_fn: Optional[callable] = None
) -> ConversationAnalyzerProtocol:
    """
    Get conversation analyzer implementation.
    
    Args:
        strategy: Analysis strategy ("hybrid", "rule_based", "llm_only")
        llm_analyze_fn: Optional LLM function for analysis
        
    Returns:
        ConversationAnalyzerProtocol implementation
    """
    if strategy == "hybrid" or strategy == "rule_based":
        return HybridConversationAnalyzer(
            llm_analyze_fn=llm_analyze_fn,
            fallback_strategy="rule_based"
        )
    elif strategy == "llm_only":
        if not llm_analyze_fn:
            raise ValueError("LLM function required for llm_only strategy")
        return HybridConversationAnalyzer(
            llm_analyze_fn=llm_analyze_fn,
            fallback_strategy="rule_based"  # Still need fallback for errors
        )
    else:
        raise ValueError(f"Unknown analyzer strategy: {strategy}")


def get_conversation_compactor(
    analyzer: ConversationAnalyzerProtocol,
    llm_summarize_fn: Optional[callable] = None,
    min_compaction_ratio: float = 0.3
) -> ConversationCompactorProtocol:
    """
    Get conversation compactor implementation.
    
    Args:
        analyzer: Conversation analyzer to use
        llm_summarize_fn: Optional LLM function for summarization
        min_compaction_ratio: Minimum compression ratio
        
    Returns:
        ConversationCompactorProtocol implementation
    """
    return IntelligentConversationCompactor(
        analyzer=analyzer,
        llm_summarize_fn=llm_summarize_fn,
        min_compaction_ratio=min_compaction_ratio
    )