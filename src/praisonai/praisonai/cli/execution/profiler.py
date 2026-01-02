"""
Profiler Module.

Provides external profiling that wraps execution.
Execution code has ZERO awareness of profiling.

Design Principles:
1. Profiler wraps execution, does not inject into it
2. Layered profiling with explicit overhead
3. Bounded resource usage
4. Versioned, stable output schema
"""

import cProfile
import pstats
import time
import platform
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from .request import ExecutionRequest
from .result import ExecutionResult
from .core import _execute_core


# Schema version - MUST be incremented for breaking changes
SCHEMA_VERSION = "1.0"

# Bounds for profile data
MAX_FUNCTION_STATS = 1000
MAX_CALL_GRAPH_EDGES = 5000
MAX_NETWORK_REQUESTS = 100
MAX_IMPORT_MODULES = 200


@dataclass
class ProfilerConfig:
    """
    Profiler configuration with explicit layer control.
    
    Layers:
    - 0: Wall-clock phases only (<1ms overhead)
    - 1: + cProfile function stats (~5% overhead)
    - 2: + Call graph callers/callees (~15% overhead)
    
    Network timing is orthogonal (opt-in via track_network).
    """
    
    # Layer control (0, 1, or 2)
    layer: int = 1
    
    # Layer 1+ options
    limit: int = 30  # Max functions to show
    sort_by: str = "cumulative"  # cumulative, time, calls
    
    # Layer 2 options
    show_callers: bool = False
    show_callees: bool = False
    
    # Network timing (orthogonal to layers)
    track_network: bool = False
    
    # Output options
    output_format: str = "text"  # text, json
    save_path: Optional[str] = None
    
    @classmethod
    def from_flags(
        cls,
        profile: bool = False,
        deep: bool = False,
        network: bool = False,
    ) -> 'ProfilerConfig':
        """Create config from CLI flags."""
        if deep:
            return cls(
                layer=2,
                show_callers=True,
                show_callees=True,
                track_network=network,
            )
        elif profile:
            return cls(layer=1, track_network=network)
        else:
            return cls(layer=0, track_network=network)


@dataclass
class TimingBreakdown:
    """
    Phase timing breakdown with full timeline visibility.
    
    All fields in milliseconds.
    Timeline order: cli_entry -> cli_parse -> routing -> imports -> agent_init -> 
                    network_start -> first_token -> first_output -> execution_end
    """
    
    # MANDATORY fields (always present)
    total_ms: float = 0.0
    imports_ms: float = 0.0
    agent_init_ms: float = 0.0
    execution_ms: float = 0.0
    
    # TIMELINE PHASES (new - for full visibility)
    cli_entry_ms: float = 0.0      # Time from ENTER to CLI entry point
    cli_parse_ms: float = 0.0      # Argparse/Typer routing time
    routing_ms: float = 0.0        # Command routing time
    network_start_ms: float = 0.0  # When network request started (relative to start)
    first_token_ms: float = 0.0    # Time to first token (streaming)
    first_output_ms: float = 0.0   # Time to First Response (TTFR) - first visible output
    
    # OPTIONAL fields (may be 0)
    tool_time_ms: float = 0.0      # If tools were called
    
    @property
    def time_to_first_response_ms(self) -> float:
        """Time to First Response (TTFR) - the key user-perceived latency metric."""
        if self.first_output_ms > 0:
            return self.first_output_ms
        # Fallback: use execution end if first_output not captured
        return self.total_ms
    
    def to_dict(self) -> Dict[str, float]:
        """Convert to dictionary."""
        return {
            "total_ms": self.total_ms,
            "imports_ms": self.imports_ms,
            "agent_init_ms": self.agent_init_ms,
            "execution_ms": self.execution_ms,
            "cli_entry_ms": self.cli_entry_ms,
            "cli_parse_ms": self.cli_parse_ms,
            "routing_ms": self.routing_ms,
            "network_start_ms": self.network_start_ms,
            "first_token_ms": self.first_token_ms,
            "first_output_ms": self.first_output_ms,
            "time_to_first_response_ms": self.time_to_first_response_ms,
            "tool_time_ms": self.tool_time_ms,
        }
    
    def to_timeline(self) -> List[Tuple[str, float, float]]:
        """
        Get ordered timeline of phases.
        
        Returns list of (phase_name, start_ms, duration_ms) tuples.
        """
        timeline = []
        cursor = 0.0
        
        # CLI Entry (if captured)
        if self.cli_entry_ms > 0:
            timeline.append(("CLI Entry", 0.0, self.cli_entry_ms))
            cursor = self.cli_entry_ms
        
        # CLI Parse
        if self.cli_parse_ms > 0:
            timeline.append(("CLI Parse", cursor, self.cli_parse_ms))
            cursor += self.cli_parse_ms
        
        # Routing
        if self.routing_ms > 0:
            timeline.append(("Routing", cursor, self.routing_ms))
            cursor += self.routing_ms
        
        # Imports
        if self.imports_ms > 0:
            timeline.append(("Imports", cursor, self.imports_ms))
            cursor += self.imports_ms
        
        # Agent Init
        if self.agent_init_ms > 0:
            timeline.append(("Agent Init", cursor, self.agent_init_ms))
            cursor += self.agent_init_ms
        
        # Network to First Token (if streaming)
        if self.network_start_ms > 0 and self.first_token_ms > 0:
            network_duration = self.first_token_ms - self.network_start_ms
            if network_duration > 0:
                timeline.append(("Network → First Token", self.network_start_ms, network_duration))
        
        # Execution
        if self.execution_ms > 0:
            timeline.append(("Execution", cursor, self.execution_ms))
        
        return timeline


@dataclass
class FunctionStat:
    """Statistics for a single function."""
    
    name: str
    file: str
    line: int
    calls: int
    total_time_ms: float
    cumulative_time_ms: float
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "file": self.file,
            "line": self.line,
            "calls": self.calls,
            "total_time_ms": self.total_time_ms,
            "cumulative_time_ms": self.cumulative_time_ms,
        }


@dataclass
class CallGraph:
    """Call graph data (callers and callees)."""
    
    callers: Dict[str, List[str]] = field(default_factory=dict)
    callees: Dict[str, List[str]] = field(default_factory=dict)
    
    @property
    def edges(self) -> List[Tuple[str, str]]:
        """Get all edges as (caller, callee) tuples."""
        edges = []
        for callee, callers in self.callers.items():
            for caller in callers:
                edges.append((caller, callee))
        return edges
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "callers": self.callers,
            "callees": self.callees,
            "edge_count": len(self.edges),
        }


@dataclass
class RequestTiming:
    """Single HTTP request timing."""
    
    url: str
    method: str
    start_time: float
    first_byte_time: float
    end_time: float
    status_code: int
    
    @property
    def ttfb_ms(self) -> float:
        """Time to first byte in milliseconds."""
        return (self.first_byte_time - self.start_time) * 1000
    
    @property
    def total_ms(self) -> float:
        """Total request time in milliseconds."""
        return (self.end_time - self.start_time) * 1000
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "url": self.url,
            "method": self.method,
            "ttfb_ms": self.ttfb_ms,
            "total_ms": self.total_ms,
            "status_code": self.status_code,
        }


@dataclass
class InvocationInfo:
    """How the profile was invoked."""
    
    method: str  # "cli_direct", "profile_command", "tui"
    flags: Dict[str, Any] = field(default_factory=dict)
    praisonai_version: str = ""
    python_version: str = ""
    
    def __post_init__(self):
        """Set version info if not provided."""
        if not self.python_version:
            self.python_version = platform.python_version()
        if not self.praisonai_version:
            try:
                from praisonai.version import __version__
                self.praisonai_version = __version__
            except ImportError:
                self.praisonai_version = "unknown"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "method": self.method,
            "flags": self.flags,
            "praisonai_version": self.praisonai_version,
            "python_version": self.python_version,
        }


@dataclass
class DecisionTrace:
    """
    Decision trace for deep profile visibility.
    
    Explains what decisions were made during execution.
    """
    
    agent_config: str = ""           # Agent configuration chosen
    model_selected: str = ""         # Model used
    streaming_mode: bool = False     # Streaming vs non-streaming
    profile_layer: int = 0           # Profile layer (0/1/2)
    tools_enabled: List[str] = field(default_factory=list)
    tools_disabled: List[str] = field(default_factory=list)
    fallbacks_used: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "agent_config": self.agent_config,
            "model_selected": self.model_selected,
            "streaming_mode": self.streaming_mode,
            "profile_layer": self.profile_layer,
            "tools_enabled": self.tools_enabled,
            "tools_disabled": self.tools_disabled,
            "fallbacks_used": self.fallbacks_used,
        }
    
    def to_text(self) -> str:
        """Format as human-readable text."""
        lines = []
        lines.append(f"  Agent Config:    {self.agent_config or 'default'}")
        lines.append(f"  Model:           {self.model_selected or 'default'}")
        lines.append(f"  Streaming:       {'enabled' if self.streaming_mode else 'disabled'}")
        lines.append(f"  Profile Layer:   {self.profile_layer}")
        if self.tools_enabled:
            lines.append(f"  Tools Enabled:   {', '.join(self.tools_enabled)}")
        if self.tools_disabled:
            lines.append(f"  Tools Disabled:  {', '.join(self.tools_disabled)}")
        if self.fallbacks_used:
            lines.append(f"  Fallbacks:       {', '.join(self.fallbacks_used)}")
        return "\n".join(lines)


@dataclass
class ModuleBreakdown:
    """
    Module/file breakdown for deep profile visibility.
    
    Groups functions by module category.
    """
    
    cli_modules: List[str] = field(default_factory=list)
    execution_modules: List[str] = field(default_factory=list)
    agent_modules: List[str] = field(default_factory=list)
    tool_modules: List[str] = field(default_factory=list)
    network_modules: List[str] = field(default_factory=list)
    third_party_modules: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, List[str]]:
        """Convert to dictionary."""
        return {
            "cli": self.cli_modules,
            "execution": self.execution_modules,
            "agent": self.agent_modules,
            "tools": self.tool_modules,
            "network": self.network_modules,
            "third_party": self.third_party_modules,
        }


@dataclass
class ProfileReport:
    """
    Canonical profile report.
    
    VERSION 1.0 - Schema is frozen after release.
    New fields MUST be optional with defaults.
    """
    
    # Schema version (MANDATORY, NEVER CHANGES MEANING)
    schema_version: str = SCHEMA_VERSION
    
    # Identity (MANDATORY)
    run_id: str = ""
    timestamp: str = ""  # ISO 8601
    
    # Invocation (MANDATORY)
    invocation: InvocationInfo = field(default_factory=lambda: InvocationInfo(method="unknown"))
    
    # Timing (MANDATORY)
    timing: TimingBreakdown = field(default_factory=TimingBreakdown)
    
    # Function stats (OPTIONAL, present if layer >= 1)
    functions: Optional[List[FunctionStat]] = None
    
    # Call graph (OPTIONAL, present if layer >= 2)
    call_graph: Optional[CallGraph] = None
    
    # Network (OPTIONAL, present if track_network)
    network: Optional[List[RequestTiming]] = None
    
    # Response (MANDATORY but truncated)
    response_preview: str = ""  # Max 500 chars
    
    # Decision trace (OPTIONAL, present if layer >= 2)
    decision_trace: Optional[DecisionTrace] = None
    
    # Module breakdown (OPTIONAL, present if layer >= 2)
    module_breakdown: Optional[ModuleBreakdown] = None
    
    def __post_init__(self):
        """Set timestamp if not provided."""
        if not self.timestamp:
            self.timestamp = datetime.utcnow().isoformat() + "Z"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result = {
            "schema_version": self.schema_version,
            "run_id": self.run_id,
            "timestamp": self.timestamp,
            "invocation": self.invocation.to_dict(),
            "timing": self.timing.to_dict(),
            "timeline": self.timing.to_timeline(),
            "timeline_diagram": self.to_timeline_diagram(),
            "response_preview": self.response_preview,
        }
        
        if self.functions is not None:
            result["functions"] = [f.to_dict() for f in self.functions]
        
        if self.call_graph is not None:
            result["call_graph"] = self.call_graph.to_dict()
        
        if self.network is not None:
            result["network"] = [r.to_dict() for r in self.network]
        
        if self.decision_trace is not None:
            result["decision_trace"] = self.decision_trace.to_dict()
        
        if self.module_breakdown is not None:
            result["module_breakdown"] = self.module_breakdown.to_dict()
        
        return result
    
    def to_json(self) -> str:
        """Convert to JSON string."""
        import json
        return json.dumps(self.to_dict(), indent=2, default=str)
    
    def to_timeline_diagram(self) -> str:
        """
        Generate ASCII timeline diagram showing execution phases.
        
        Format:
        ENTER ─────────────────────────────────────────────────────────► RESPONSE
               │ imports │ init │        network        │
               │  XXXms  │ XXms │        XXXms          │
               └─────────┴──────┴───────────────────────┘
                                                  TOTAL: XXXXms
        """
        lines = []
        total = self.timing.total_ms
        if total <= 0:
            return "No timing data available"
        
        # Calculate phase widths (proportional to time, min 8 chars)
        phases = []
        if self.timing.imports_ms > 0:
            phases.append(("imports", self.timing.imports_ms))
        if self.timing.agent_init_ms > 0:
            phases.append(("init", self.timing.agent_init_ms))
        if self.timing.execution_ms > 0:
            phases.append(("network", self.timing.execution_ms))
        
        if not phases:
            phases = [("total", total)]
        
        # Scale to fit in ~60 chars
        scale = 50.0 / total if total > 0 else 1
        
        # Build the diagram
        lines.append("")
        lines.append("## Timeline Diagram")
        lines.append("")
        
        # Top line with arrow
        top_line = "ENTER "
        for name, ms in phases:
            width = max(8, int(ms * scale))
            top_line += "─" * width
        top_line += "► RESPONSE"
        lines.append(top_line)
        
        # Phase names line
        name_line = "      "
        for name, ms in phases:
            width = max(8, int(ms * scale))
            name_line += "│" + name.center(width - 1)
        name_line += "│"
        lines.append(name_line)
        
        # Phase times line
        time_line = "      "
        for name, ms in phases:
            width = max(8, int(ms * scale))
            time_str = f"{ms:.0f}ms"
            time_line += "│" + time_str.center(width - 1)
        time_line += "│"
        lines.append(time_line)
        
        # Bottom line
        bottom_line = "      "
        for i, (name, ms) in enumerate(phases):
            width = max(8, int(ms * scale))
            if i == 0:
                bottom_line += "└" + "─" * (width - 1)
            else:
                bottom_line += "┴" + "─" * (width - 1)
        bottom_line += "┘"
        lines.append(bottom_line)
        
        # Total line
        total_line = " " * (len(bottom_line) - 15) + f"TOTAL: {total:.0f}ms"
        lines.append(total_line)
        lines.append("")
        
        return "\n".join(lines)
    
    def to_text(self) -> str:
        """Format as human-readable text."""
        lines = []
        lines.append("=" * 70)
        lines.append("PraisonAI Profile Report")
        lines.append("=" * 70)
        lines.append("")
        
        # Identity
        lines.append(f"Run ID:     {self.run_id}")
        lines.append(f"Timestamp:  {self.timestamp}")
        lines.append(f"Method:     {self.invocation.method}")
        lines.append(f"Version:    {self.invocation.praisonai_version}")
        lines.append("")
        
        # TIMELINE DIAGRAM (visual representation)
        lines.append(self.to_timeline_diagram())
        
        # TIMELINE SECTION (shows ENTER → First Response)
        lines.append("## Execution Timeline")
        lines.append("-" * 45)
        timeline = self.timing.to_timeline()
        if timeline:
            for phase_name, start_ms, duration_ms in timeline:
                lines.append(f"  {phase_name:<25} : {duration_ms:>8.2f} ms")
        else:
            # Fallback to basic phases
            if self.timing.imports_ms > 0:
                lines.append(f"  {'Imports':<25} : {self.timing.imports_ms:>8.2f} ms")
            if self.timing.agent_init_ms > 0:
                lines.append(f"  {'Agent Init':<25} : {self.timing.agent_init_ms:>8.2f} ms")
            if self.timing.execution_ms > 0:
                lines.append(f"  {'Execution':<25} : {self.timing.execution_ms:>8.2f} ms")
        lines.append("  " + "─" * 43)
        
        # TIME TO FIRST RESPONSE (TTFR) - the key metric
        ttfr = self.timing.time_to_first_response_ms
        lines.append(f"  {'⏱ Time to First Response':<25} : {ttfr:>8.2f} ms")
        lines.append(f"  {'TOTAL':<25} : {self.timing.total_ms:>8.2f} ms")
        lines.append("")
        
        # Timing breakdown (legacy format for compatibility)
        lines.append("## Timing Breakdown")
        lines.append("-" * 40)
        if self.timing.cli_entry_ms > 0:
            lines.append(f"  CLI Entry:      {self.timing.cli_entry_ms:>10.2f} ms")
        if self.timing.cli_parse_ms > 0:
            lines.append(f"  CLI Parse:      {self.timing.cli_parse_ms:>10.2f} ms")
        if self.timing.routing_ms > 0:
            lines.append(f"  Routing:        {self.timing.routing_ms:>10.2f} ms")
        lines.append(f"  Imports:        {self.timing.imports_ms:>10.2f} ms")
        lines.append(f"  Agent Init:     {self.timing.agent_init_ms:>10.2f} ms")
        lines.append(f"  Execution:      {self.timing.execution_ms:>10.2f} ms")
        if self.timing.network_start_ms > 0:
            lines.append(f"  Network Start:  {self.timing.network_start_ms:>10.2f} ms")
        if self.timing.first_token_ms > 0:
            lines.append(f"  First Token:    {self.timing.first_token_ms:>10.2f} ms")
        if self.timing.first_output_ms > 0:
            lines.append(f"  First Output:   {self.timing.first_output_ms:>10.2f} ms")
        lines.append("  ─────────────────────────────────────")
        lines.append(f"  TOTAL:          {self.timing.total_ms:>10.2f} ms")
        lines.append("")
        
        # Decision trace (deep profile only)
        if self.decision_trace:
            lines.append("## Decision Trace")
            lines.append("-" * 40)
            lines.append(self.decision_trace.to_text())
            lines.append("")
        
        # Function stats
        if self.functions:
            lines.append("## Top Functions by Cumulative Time")
            lines.append("-" * 70)
            lines.append(f"{'Function':<40} {'Calls':>8} {'Cumul (ms)':>12}")
            lines.append("-" * 70)
            for func in self.functions[:20]:
                name = func.name[:38] if len(func.name) > 38 else func.name
                lines.append(f"{name:<40} {func.calls:>8} {func.cumulative_time_ms:>12.2f}")
            lines.append("")
        
        # Module breakdown (deep profile only)
        if self.module_breakdown:
            lines.append("## Module Breakdown")
            lines.append("-" * 40)
            mb = self.module_breakdown
            if mb.cli_modules:
                lines.append(f"  CLI:        {len(mb.cli_modules)} modules")
            if mb.execution_modules:
                lines.append(f"  Execution:  {len(mb.execution_modules)} modules")
            if mb.agent_modules:
                lines.append(f"  Agent:      {len(mb.agent_modules)} modules")
            if mb.tool_modules:
                lines.append(f"  Tools:      {len(mb.tool_modules)} modules")
            if mb.network_modules:
                lines.append(f"  Network:    {len(mb.network_modules)} modules")
            if mb.third_party_modules:
                lines.append(f"  Third-party:{len(mb.third_party_modules)} modules")
            lines.append("")
        
        # Call graph summary
        if self.call_graph:
            lines.append(f"## Call Graph: {len(self.call_graph.edges)} edges")
            lines.append("")
        
        # Network timing
        if self.network:
            lines.append("## Network Requests")
            lines.append("-" * 70)
            for req in self.network[:10]:
                lines.append(f"  {req.method} {req.url[:50]} - {req.total_ms:.2f}ms (TTFB: {req.ttfb_ms:.2f}ms)")
            lines.append("")
        
        # Response preview
        if self.response_preview:
            lines.append("## Response Preview")
            lines.append("-" * 40)
            preview = self.response_preview[:200]
            if len(self.response_preview) > 200:
                preview += "..."
            lines.append(preview)
            lines.append("")
        
        lines.append("=" * 70)
        
        return "\n".join(lines)


class Profiler:
    """
    External profiler that wraps execution.
    
    Execution code has ZERO awareness of profiling.
    Profiler uses cProfile.runctx() or similar.
    """
    
    def __init__(self, config: ProfilerConfig):
        self.config = config
        self._cprofile: Optional[cProfile.Profile] = None
        self._timing: Dict[str, float] = {}
        self._network_requests: List[RequestTiming] = []
    
    def profile_sync(
        self,
        request: ExecutionRequest,
        invocation_method: str = "profile_command",
    ) -> Tuple[ExecutionResult, ProfileReport]:
        """
        Profile synchronous execution.
        
        Args:
            request: The execution request
            invocation_method: How this was invoked (for report)
        
        Returns:
            Tuple of (ExecutionResult, ProfileReport)
        """
        timing_dict: Dict[str, float] = {}
        
        # Layer 0: Wall-clock timing (always)
        start = time.perf_counter()
        
        # Layer 1+: cProfile
        if self.config.layer >= 1:
            self._cprofile = cProfile.Profile()
            self._cprofile.enable()
        
        try:
            result = _execute_core(request, timing_dict)
        finally:
            if self._cprofile:
                self._cprofile.disable()
        
        total_ms = (time.perf_counter() - start) * 1000
        
        # Build report
        report = self._build_report(
            request=request,
            result=result,
            timing_dict=timing_dict,
            total_ms=total_ms,
            invocation_method=invocation_method,
        )
        
        return result, report
    
    def _build_report(
        self,
        request: ExecutionRequest,
        result: ExecutionResult,
        timing_dict: Dict[str, float],
        total_ms: float,
        invocation_method: str,
    ) -> ProfileReport:
        """Build the profile report from collected data."""
        
        # Calculate first_output_ms (TTFR) - time from start to when output is available
        # This is imports + agent_init + execution (when output becomes available)
        imports_ms = timing_dict.get("imports_ms", 0.0)
        agent_init_ms = timing_dict.get("agent_init_ms", 0.0)
        execution_ms = timing_dict.get("execution_ms", 0.0)
        first_output_ms = imports_ms + agent_init_ms + execution_ms
        
        # Timing breakdown with full timeline
        timing = TimingBreakdown(
            total_ms=total_ms,
            imports_ms=imports_ms,
            agent_init_ms=agent_init_ms,
            execution_ms=execution_ms,
            cli_entry_ms=timing_dict.get("cli_entry_ms", 0.0),
            cli_parse_ms=timing_dict.get("cli_parse_ms", 0.0),
            routing_ms=timing_dict.get("routing_ms", 0.0),
            network_start_ms=timing_dict.get("network_start_ms", 0.0),
            first_token_ms=timing_dict.get("first_token_ms", 0.0),
            first_output_ms=first_output_ms,
        )
        
        # Invocation info
        invocation = InvocationInfo(
            method=invocation_method,
            flags={
                "layer": self.config.layer,
                "stream": request.stream,
                "model": request.model,
            },
        )
        
        # Function stats (layer 1+)
        functions = None
        if self.config.layer >= 1 and self._cprofile:
            functions = self._extract_function_stats()
        
        # Call graph (layer 2)
        call_graph = None
        if self.config.layer >= 2 and self._cprofile:
            call_graph = self._extract_call_graph()
        
        # Decision trace (layer 2 - deep profile)
        decision_trace = None
        if self.config.layer >= 2:
            decision_trace = DecisionTrace(
                agent_config=request.agent_name or "default",
                model_selected=request.model or "default",
                streaming_mode=request.stream,
                profile_layer=self.config.layer,
                tools_enabled=list(request.tools) if request.tools else [],
                tools_disabled=[],
                fallbacks_used=[],
            )
        
        # Module breakdown (layer 2 - deep profile)
        module_breakdown = None
        if self.config.layer >= 2 and functions:
            module_breakdown = self._extract_module_breakdown(functions)
        
        # Response preview (truncated)
        response_preview = result.output[:500] if result.output else ""
        
        return ProfileReport(
            run_id=result.run_id,
            invocation=invocation,
            timing=timing,
            functions=functions,
            call_graph=call_graph,
            network=self._network_requests if self._network_requests else None,
            response_preview=response_preview,
            decision_trace=decision_trace,
            module_breakdown=module_breakdown,
        )
    
    def _extract_module_breakdown(self, functions: List[FunctionStat]) -> ModuleBreakdown:
        """Extract module breakdown from function stats."""
        cli_modules = set()
        execution_modules = set()
        agent_modules = set()
        tool_modules = set()
        network_modules = set()
        third_party_modules = set()
        
        for func in functions:
            file_path = func.file.lower()
            
            if "praisonai/cli" in file_path:
                cli_modules.add(func.file)
            elif "praisonai" in file_path and "execution" in file_path:
                execution_modules.add(func.file)
            elif "praisonaiagents" in file_path and "agent" in file_path:
                agent_modules.add(func.file)
            elif "praisonaiagents" in file_path and "tool" in file_path:
                tool_modules.add(func.file)
            elif any(x in file_path for x in ["httpx", "httpcore", "urllib", "requests", "aiohttp"]):
                network_modules.add(func.file)
            elif "site-packages" in file_path or not file_path.startswith("/"):
                third_party_modules.add(func.file)
        
        return ModuleBreakdown(
            cli_modules=list(cli_modules)[:20],
            execution_modules=list(execution_modules)[:20],
            agent_modules=list(agent_modules)[:20],
            tool_modules=list(tool_modules)[:20],
            network_modules=list(network_modules)[:20],
            third_party_modules=list(third_party_modules)[:20],
        )
    
    def _extract_function_stats(self) -> List[FunctionStat]:
        """Extract function statistics from cProfile."""
        if not self._cprofile:
            return []
        
        stats = pstats.Stats(self._cprofile)
        
        # Sort by cumulative time
        stats.sort_stats(self.config.sort_by)
        
        # Extract stats
        function_stats = []
        for (filename, line, name), (cc, nc, tt, ct, callers) in stats.stats.items():
            if len(function_stats) >= MAX_FUNCTION_STATS:
                break
            
            function_stats.append(FunctionStat(
                name=name,
                file=filename,
                line=line,
                calls=nc,
                total_time_ms=tt * 1000,
                cumulative_time_ms=ct * 1000,
            ))
        
        # Sort and limit
        function_stats.sort(key=lambda x: x.cumulative_time_ms, reverse=True)
        return function_stats[:self.config.limit]
    
    def _extract_call_graph(self) -> CallGraph:
        """Extract call graph from cProfile."""
        if not self._cprofile:
            return CallGraph()
        
        stats = pstats.Stats(self._cprofile)
        
        callers: Dict[str, List[str]] = {}
        callees: Dict[str, List[str]] = {}
        edge_count = 0
        
        for (filename, line, name), (cc, nc, tt, ct, caller_dict) in stats.stats.items():
            if edge_count >= MAX_CALL_GRAPH_EDGES:
                break
            
            callee_key = f"{name}:{filename}:{line}"
            
            for (caller_file, caller_line, caller_name), _ in caller_dict.items():
                if edge_count >= MAX_CALL_GRAPH_EDGES:
                    break
                
                caller_key = f"{caller_name}:{caller_file}:{caller_line}"
                
                # Add to callers
                if callee_key not in callers:
                    callers[callee_key] = []
                if caller_key not in callers[callee_key]:
                    callers[callee_key].append(caller_key)
                
                # Add to callees
                if caller_key not in callees:
                    callees[caller_key] = []
                if callee_key not in callees[caller_key]:
                    callees[caller_key].append(callee_key)
                
                edge_count += 1
        
        return CallGraph(callers=callers, callees=callees)
