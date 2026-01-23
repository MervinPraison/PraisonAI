"""
Context Trace Analyzer for PraisonAI.

Provides analysis utilities for context traces:
- Token usage statistics
- Cost calculation and breakdown
- Duplicate content detection
- Context efficiency metrics
"""

import hashlib
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple


@dataclass
class TokenStats:
    """Token usage statistics."""
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    total_tokens: int = 0
    by_agent: Dict[str, Dict[str, int]] = field(default_factory=dict)
    
    def add(self, agent_name: str, prompt_tokens: int, completion_tokens: int) -> None:
        """Add token usage for an agent."""
        self.total_prompt_tokens += prompt_tokens
        self.total_completion_tokens += completion_tokens
        self.total_tokens += prompt_tokens + completion_tokens
        
        if agent_name not in self.by_agent:
            self.by_agent[agent_name] = {"prompt": 0, "completion": 0, "total": 0}
        
        self.by_agent[agent_name]["prompt"] += prompt_tokens
        self.by_agent[agent_name]["completion"] += completion_tokens
        self.by_agent[agent_name]["total"] += prompt_tokens + completion_tokens


@dataclass
class CostStats:
    """Cost statistics."""
    total_llm_cost: float = 0.0
    total_tool_cost: float = 0.0
    total_cost: float = 0.0
    llm_calls: int = 0
    tool_calls: int = 0
    by_agent: Dict[str, Dict[str, float]] = field(default_factory=dict)
    by_tool: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    
    def add_llm_cost(self, agent_name: str, cost: float) -> None:
        """Add LLM cost for an agent."""
        self.total_llm_cost += cost
        self.total_cost += cost
        self.llm_calls += 1
        
        if agent_name not in self.by_agent:
            self.by_agent[agent_name] = {"llm": 0.0, "tool": 0.0, "total": 0.0}
        
        self.by_agent[agent_name]["llm"] += cost
        self.by_agent[agent_name]["total"] += cost
    
    def add_tool_cost(self, agent_name: str, tool_name: str, cost: float) -> None:
        """Add tool cost."""
        self.total_tool_cost += cost
        self.total_cost += cost
        self.tool_calls += 1
        
        if agent_name not in self.by_agent:
            self.by_agent[agent_name] = {"llm": 0.0, "tool": 0.0, "total": 0.0}
        
        self.by_agent[agent_name]["tool"] += cost
        self.by_agent[agent_name]["total"] += cost
        
        if tool_name not in self.by_tool:
            self.by_tool[tool_name] = {"count": 0, "cost": 0.0}
        
        self.by_tool[tool_name]["count"] += 1
        self.by_tool[tool_name]["cost"] += cost


@dataclass
class DuplicateInfo:
    """Information about duplicate content."""
    content_hash: str
    first_occurrence: int  # Event sequence number
    first_agent: str
    duplicates: List[Tuple[int, str]] = field(default_factory=list)  # (seq_num, agent_name)
    estimated_tokens: int = 0
    
    @property
    def duplicate_count(self) -> int:
        return len(self.duplicates)
    
    @property
    def wasted_tokens(self) -> int:
        return self.estimated_tokens * self.duplicate_count


@dataclass
class ContextFlowInfo:
    """Information about context flow between agents."""
    from_agent: str
    to_agent: str
    tokens_passed: int = 0
    messages_passed: int = 0
    timestamp: float = 0.0


@dataclass
class AnalysisResult:
    """Complete analysis result."""
    session_id: str
    total_events: int
    duration_seconds: float
    agents: List[str]
    token_stats: TokenStats
    cost_stats: CostStats
    duplicates: List[DuplicateInfo]
    context_flow: List[ContextFlowInfo]
    
    @property
    def total_wasted_tokens(self) -> int:
        return sum(d.wasted_tokens for d in self.duplicates)
    
    @property
    def duplicate_count(self) -> int:
        return sum(d.duplicate_count for d in self.duplicates)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "session_id": self.session_id,
            "total_events": self.total_events,
            "duration_seconds": round(self.duration_seconds, 2),
            "agents": self.agents,
            "token_stats": {
                "total_prompt_tokens": self.token_stats.total_prompt_tokens,
                "total_completion_tokens": self.token_stats.total_completion_tokens,
                "total_tokens": self.token_stats.total_tokens,
                "by_agent": self.token_stats.by_agent,
            },
            "cost_stats": {
                "total_llm_cost": round(self.cost_stats.total_llm_cost, 6),
                "total_tool_cost": round(self.cost_stats.total_tool_cost, 6),
                "total_cost": round(self.cost_stats.total_cost, 6),
                "llm_calls": self.cost_stats.llm_calls,
                "tool_calls": self.cost_stats.tool_calls,
                "by_agent": {k: {kk: round(vv, 6) for kk, vv in v.items()} 
                           for k, v in self.cost_stats.by_agent.items()},
                "by_tool": self.cost_stats.by_tool,
            },
            "duplicates": {
                "count": self.duplicate_count,
                "wasted_tokens": self.total_wasted_tokens,
                "details": [
                    {
                        "hash": d.content_hash[:16],
                        "first_agent": d.first_agent,
                        "first_event": d.first_occurrence,
                        "duplicate_count": d.duplicate_count,
                        "estimated_tokens": d.estimated_tokens,
                        "wasted_tokens": d.wasted_tokens,
                    }
                    for d in self.duplicates
                ],
            },
            "context_flow": [
                {
                    "from": f.from_agent,
                    "to": f.to_agent,
                    "tokens": f.tokens_passed,
                    "messages": f.messages_passed,
                }
                for f in self.context_flow
            ],
        }


def compute_content_hash(content: str) -> str:
    """Compute SHA256 hash of content for duplicate detection."""
    return hashlib.sha256(content.encode('utf-8')).hexdigest()


def estimate_tokens(text: str) -> int:
    """Estimate token count from text (rough approximation: 4 chars per token)."""
    return len(text) // 4


class TraceAnalyzer:
    """
    Analyzer for context trace events.
    
    Provides statistics, cost breakdown, and duplicate detection.
    
    Usage:
        analyzer = TraceAnalyzer(events)
        result = analyzer.analyze()
        print(result.token_stats.total_tokens)
    """
    
    def __init__(self, events: List[Any]):
        """
        Initialize analyzer with events.
        
        Args:
            events: List of ContextEvent objects or dicts
        """
        self._events = events
        self._content_hashes: Dict[str, DuplicateInfo] = {}
    
    def analyze(self) -> AnalysisResult:
        """
        Perform full analysis of trace events.
        
        Returns:
            AnalysisResult with all statistics
        """
        token_stats = TokenStats()
        cost_stats = CostStats()
        agents: Set[str] = set()
        context_flow: List[ContextFlowInfo] = []
        
        start_time = None
        end_time = None
        
        for event in self._events:
            # Get event attributes (handle both objects and dicts)
            event_type = self._get_attr(event, 'event_type')
            if hasattr(event_type, 'value'):
                event_type = event_type.value
            
            agent_name = self._get_attr(event, 'agent_name') or "unknown"
            timestamp = self._get_attr(event, 'timestamp') or 0
            data = self._get_attr(event, 'data') or {}
            
            # Track time range
            if timestamp:
                if start_time is None or timestamp < start_time:
                    start_time = timestamp
                if end_time is None or timestamp > end_time:
                    end_time = timestamp
            
            # Track agents
            if agent_name and agent_name != "unknown":
                agents.add(agent_name)
            
            # Process by event type
            if event_type == "llm_response":
                prompt_tokens = self._get_attr(event, 'prompt_tokens') or 0
                completion_tokens = self._get_attr(event, 'completion_tokens') or 0
                cost_usd = self._get_attr(event, 'cost_usd') or 0.0
                
                token_stats.add(agent_name, prompt_tokens, completion_tokens)
                cost_stats.add_llm_cost(agent_name, cost_usd)
                
                # Check for duplicate content in response
                response_content = data.get('response_content', '')
                if response_content:
                    self._track_content(
                        response_content,
                        self._get_attr(event, 'sequence_num') or 0,
                        agent_name
                    )
            
            elif event_type == "llm_request":
                # Check for duplicate messages
                messages = data.get('messages', [])
                for msg in messages:
                    if isinstance(msg, dict):
                        content = msg.get('content', '')
                        if content and len(content) > 100:  # Only track substantial content
                            self._track_content(
                                content,
                                self._get_attr(event, 'sequence_num') or 0,
                                agent_name
                            )
            
            elif event_type == "tool_call_end":
                tool_name = data.get('tool_name', 'unknown')
                cost_usd = self._get_attr(event, 'cost_usd') or 0.0
                cost_stats.add_tool_cost(agent_name, tool_name, cost_usd)
            
            elif event_type == "agent_handoff":
                from_agent = data.get('from_agent', '')
                to_agent = data.get('to_agent', '')
                context_passed = data.get('context_passed', {})
                
                # Estimate tokens passed
                tokens_passed = 0
                if context_passed:
                    tokens_passed = estimate_tokens(str(context_passed))
                
                context_flow.append(ContextFlowInfo(
                    from_agent=from_agent,
                    to_agent=to_agent,
                    tokens_passed=tokens_passed,
                    messages_passed=len(context_passed) if isinstance(context_passed, list) else 1,
                    timestamp=timestamp,
                ))
        
        # Calculate duration
        duration = (end_time - start_time) if start_time and end_time else 0.0
        
        # Get duplicates with actual duplicates (not just first occurrences)
        duplicates = [d for d in self._content_hashes.values() if d.duplicate_count > 0]
        
        return AnalysisResult(
            session_id=self._get_attr(self._events[0], 'session_id') if self._events else "",
            total_events=len(self._events),
            duration_seconds=duration,
            agents=sorted(agents),
            token_stats=token_stats,
            cost_stats=cost_stats,
            duplicates=duplicates,
            context_flow=context_flow,
        )
    
    def _get_attr(self, obj: Any, name: str) -> Any:
        """Get attribute from object or dict."""
        if isinstance(obj, dict):
            return obj.get(name)
        return getattr(obj, name, None)
    
    def _track_content(self, content: str, seq_num: int, agent_name: str) -> None:
        """Track content for duplicate detection."""
        content_hash = compute_content_hash(content)
        
        if content_hash in self._content_hashes:
            # This is a duplicate
            existing = self._content_hashes[content_hash]
            existing.duplicates.append((seq_num, agent_name))
        else:
            # First occurrence
            self._content_hashes[content_hash] = DuplicateInfo(
                content_hash=content_hash,
                first_occurrence=seq_num,
                first_agent=agent_name,
                estimated_tokens=estimate_tokens(content),
            )


def format_stats_output(result: AnalysisResult) -> str:
    """
    Format analysis result as human-readable text.
    
    Args:
        result: AnalysisResult from TraceAnalyzer
        
    Returns:
        Formatted string for display
    """
    lines = []
    
    lines.append("=" * 60)
    lines.append(f"  SESSION STATISTICS: {result.session_id}")
    lines.append("=" * 60)
    lines.append("")
    
    # Basic info
    lines.append(f"  Duration:        {result.duration_seconds:.1f} seconds")
    lines.append(f"  Agents:          {len(result.agents)} ({', '.join(result.agents)})")
    lines.append(f"  Total Events:    {result.total_events}")
    lines.append("")
    
    # Token usage
    lines.append("  TOKEN USAGE:")
    lines.append(f"    Total Prompt:      {result.token_stats.total_prompt_tokens:,} tokens")
    lines.append(f"    Total Completion:  {result.token_stats.total_completion_tokens:,} tokens")
    lines.append(f"    Total:             {result.token_stats.total_tokens:,} tokens")
    
    if result.token_stats.by_agent:
        lines.append("")
        lines.append("    By Agent:")
        for agent, stats in result.token_stats.by_agent.items():
            lines.append(f"      {agent}: {stats['total']:,} tokens (prompt: {stats['prompt']:,}, completion: {stats['completion']:,})")
    lines.append("")
    
    # Cost breakdown
    lines.append("  COST BREAKDOWN:")
    lines.append(f"    LLM Calls:        ${result.cost_stats.total_llm_cost:.4f} ({result.cost_stats.llm_calls} calls)")
    lines.append(f"    Tool Calls:       ${result.cost_stats.total_tool_cost:.4f} ({result.cost_stats.tool_calls} calls)")
    lines.append(f"    Total:            ${result.cost_stats.total_cost:.4f}")
    
    if result.cost_stats.by_tool:
        lines.append("")
        lines.append("    By Tool:")
        for tool, stats in result.cost_stats.by_tool.items():
            lines.append(f"      {tool}: ${stats['cost']:.4f} ({stats['count']} calls)")
    lines.append("")
    
    # Context efficiency
    lines.append("  CONTEXT EFFICIENCY:")
    if result.duplicates:
        lines.append(f"    Duplicates Found: {result.duplicate_count}")
        lines.append(f"    Wasted Tokens:    {result.total_wasted_tokens:,}")
        lines.append("")
        lines.append("    Duplicate Details:")
        for dup in result.duplicates[:5]:  # Show top 5
            lines.append(f"      - Hash {dup.content_hash[:12]}... from {dup.first_agent}")
            lines.append(f"        Duplicated {dup.duplicate_count}x, ~{dup.wasted_tokens:,} wasted tokens")
        if len(result.duplicates) > 5:
            lines.append(f"      ... and {len(result.duplicates) - 5} more")
    else:
        lines.append("    Duplicates Found: 0")
        lines.append("    Context is optimized!")
    
    if result.context_flow:
        lines.append("")
        lines.append("    Context Flow:")
        for flow in result.context_flow:
            lines.append(f"      {flow.from_agent} → {flow.to_agent}: ~{flow.tokens_passed:,} tokens")
    
    lines.append("")
    lines.append("=" * 60)
    
    return "\n".join(lines)


def format_cost_output(result: AnalysisResult) -> str:
    """
    Format cost-focused output.
    
    Args:
        result: AnalysisResult from TraceAnalyzer
        
    Returns:
        Formatted string for display
    """
    lines = []
    
    lines.append("=" * 60)
    lines.append(f"  COST REPORT: {result.session_id}")
    lines.append("=" * 60)
    lines.append("")
    
    lines.append(f"  TOTAL COST: ${result.cost_stats.total_cost:.4f}")
    lines.append("")
    
    lines.append("  LLM COSTS:")
    lines.append(f"    Calls:  {result.cost_stats.llm_calls}")
    lines.append(f"    Cost:   ${result.cost_stats.total_llm_cost:.4f}")
    
    if result.cost_stats.by_agent:
        lines.append("")
        lines.append("    By Agent:")
        for agent, stats in result.cost_stats.by_agent.items():
            lines.append(f"      {agent}: ${stats['llm']:.4f}")
    lines.append("")
    
    lines.append("  TOOL COSTS (1 credit = $0.001):")
    lines.append(f"    Calls:   {result.cost_stats.tool_calls}")
    lines.append(f"    Credits: {int(result.cost_stats.total_tool_cost * 1000)}")
    lines.append(f"    Cost:    ${result.cost_stats.total_tool_cost:.4f}")
    
    if result.cost_stats.by_tool:
        lines.append("")
        lines.append("    By Tool:")
        for tool, stats in result.cost_stats.by_tool.items():
            credits = int(stats['cost'] * 1000)
            lines.append(f"      {tool}: {credits} credits (${stats['cost']:.4f})")
    
    lines.append("")
    lines.append("=" * 60)
    
    return "\n".join(lines)
