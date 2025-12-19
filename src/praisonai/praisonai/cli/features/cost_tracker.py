"""
Cost Tracking System for PraisonAI CLI.

Inspired by Aider's cost tracking and Gemini CLI's stats command.
Provides real-time cost and token usage tracking.

Architecture:
- CostTracker: Tracks tokens and costs per session
- ModelPricing: Pricing data for different models
- UsageStats: Aggregated usage statistics
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from datetime import datetime
import logging
import json

logger = logging.getLogger(__name__)


# ============================================================================
# Model Pricing Data
# ============================================================================

@dataclass
class ModelPricing:
    """
    Pricing information for a model.
    
    Prices are per 1M tokens (as commonly quoted).
    """
    model_name: str
    input_price_per_1m: float  # Price per 1M input tokens
    output_price_per_1m: float  # Price per 1M output tokens
    context_window: int = 128000
    
    def calculate_cost(self, input_tokens: int, output_tokens: int) -> float:
        """Calculate cost for given token counts."""
        input_cost = (input_tokens / 1_000_000) * self.input_price_per_1m
        output_cost = (output_tokens / 1_000_000) * self.output_price_per_1m
        return input_cost + output_cost


# Default pricing for common models (as of late 2024)
DEFAULT_PRICING: Dict[str, ModelPricing] = {
    # OpenAI models
    "gpt-4o": ModelPricing("gpt-4o", 2.50, 10.00, 128000),
    "gpt-4o-mini": ModelPricing("gpt-4o-mini", 0.15, 0.60, 128000),
    "gpt-4-turbo": ModelPricing("gpt-4-turbo", 10.00, 30.00, 128000),
    "gpt-4": ModelPricing("gpt-4", 30.00, 60.00, 8192),
    "gpt-3.5-turbo": ModelPricing("gpt-3.5-turbo", 0.50, 1.50, 16385),
    "o1": ModelPricing("o1", 15.00, 60.00, 200000),
    "o1-mini": ModelPricing("o1-mini", 3.00, 12.00, 128000),
    "o1-preview": ModelPricing("o1-preview", 15.00, 60.00, 128000),
    "o3-mini": ModelPricing("o3-mini", 1.10, 4.40, 200000),
    
    # Anthropic models
    "claude-3-5-sonnet-20241022": ModelPricing("claude-3-5-sonnet", 3.00, 15.00, 200000),
    "claude-3-5-sonnet": ModelPricing("claude-3-5-sonnet", 3.00, 15.00, 200000),
    "claude-3-opus": ModelPricing("claude-3-opus", 15.00, 75.00, 200000),
    "claude-3-sonnet": ModelPricing("claude-3-sonnet", 3.00, 15.00, 200000),
    "claude-3-haiku": ModelPricing("claude-3-haiku", 0.25, 1.25, 200000),
    
    # Google models
    "gemini-2.0-flash": ModelPricing("gemini-2.0-flash", 0.10, 0.40, 1000000),
    "gemini-1.5-pro": ModelPricing("gemini-1.5-pro", 1.25, 5.00, 2000000),
    "gemini-1.5-flash": ModelPricing("gemini-1.5-flash", 0.075, 0.30, 1000000),
    
    # Default fallback
    "default": ModelPricing("default", 1.00, 3.00, 128000),
}


def get_pricing(model_name: str) -> ModelPricing:
    """Get pricing for a model, with fallback to default."""
    # Try exact match
    if model_name in DEFAULT_PRICING:
        return DEFAULT_PRICING[model_name]
    
    # Try partial match
    model_lower = model_name.lower()
    for key, pricing in DEFAULT_PRICING.items():
        if key in model_lower or model_lower in key:
            return pricing
    
    # Return default
    logger.debug(f"No pricing found for model '{model_name}', using default")
    return DEFAULT_PRICING["default"]


# ============================================================================
# Usage Statistics
# ============================================================================

@dataclass
class TokenUsage:
    """Token usage for a single request."""
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    cached_tokens: int = 0
    
    def __post_init__(self):
        if self.total_tokens == 0:
            self.total_tokens = self.input_tokens + self.output_tokens


@dataclass
class RequestStats:
    """Statistics for a single request."""
    timestamp: datetime
    model: str
    usage: TokenUsage
    cost: float
    duration_ms: float = 0.0
    prompt_preview: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "model": self.model,
            "input_tokens": self.usage.input_tokens,
            "output_tokens": self.usage.output_tokens,
            "total_tokens": self.usage.total_tokens,
            "cached_tokens": self.usage.cached_tokens,
            "cost": self.cost,
            "duration_ms": self.duration_ms,
        }


@dataclass
class SessionStats:
    """Aggregated statistics for a session."""
    session_id: str
    start_time: datetime
    end_time: Optional[datetime] = None
    
    total_requests: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_tokens: int = 0
    total_cached_tokens: int = 0
    total_cost: float = 0.0
    total_duration_ms: float = 0.0
    
    models_used: Dict[str, int] = field(default_factory=dict)
    
    def add_request(self, stats: RequestStats) -> None:
        """Add request statistics to session totals."""
        self.total_requests += 1
        self.total_input_tokens += stats.usage.input_tokens
        self.total_output_tokens += stats.usage.output_tokens
        self.total_tokens += stats.usage.total_tokens
        self.total_cached_tokens += stats.usage.cached_tokens
        self.total_cost += stats.cost
        self.total_duration_ms += stats.duration_ms
        
        # Track model usage
        if stats.model not in self.models_used:
            self.models_used[stats.model] = 0
        self.models_used[stats.model] += 1
    
    @property
    def duration_seconds(self) -> float:
        """Get session duration in seconds."""
        end = self.end_time or datetime.now()
        return (end - self.start_time).total_seconds()
    
    @property
    def avg_tokens_per_request(self) -> float:
        """Get average tokens per request."""
        if self.total_requests == 0:
            return 0.0
        return self.total_tokens / self.total_requests
    
    @property
    def avg_cost_per_request(self) -> float:
        """Get average cost per request."""
        if self.total_requests == 0:
            return 0.0
        return self.total_cost / self.total_requests
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "session_id": self.session_id,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "duration_seconds": self.duration_seconds,
            "total_requests": self.total_requests,
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "total_tokens": self.total_tokens,
            "total_cached_tokens": self.total_cached_tokens,
            "total_cost": self.total_cost,
            "avg_tokens_per_request": self.avg_tokens_per_request,
            "avg_cost_per_request": self.avg_cost_per_request,
            "models_used": self.models_used,
        }


# ============================================================================
# Cost Tracker
# ============================================================================

class CostTracker:
    """
    Tracks costs and token usage for a session.
    
    Features:
    - Real-time cost tracking
    - Per-model statistics
    - Session history
    - Export to JSON
    """
    
    def __init__(
        self,
        session_id: Optional[str] = None,
        pricing: Optional[Dict[str, ModelPricing]] = None,
        verbose: bool = False
    ):
        self.session_id = session_id or self._generate_session_id()
        self.pricing = pricing or DEFAULT_PRICING
        self.verbose = verbose
        
        self.session_stats = SessionStats(
            session_id=self.session_id,
            start_time=datetime.now()
        )
        self.request_history: List[RequestStats] = []
    
    def _generate_session_id(self) -> str:
        """Generate a unique session ID."""
        import uuid
        return str(uuid.uuid4())[:8]
    
    def track_request(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cached_tokens: int = 0,
        duration_ms: float = 0.0,
        prompt_preview: str = ""
    ) -> RequestStats:
        """
        Track a single request.
        
        Returns:
            RequestStats for the tracked request
        """
        usage = TokenUsage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cached_tokens=cached_tokens
        )
        
        # Calculate cost
        pricing = get_pricing(model)
        cost = pricing.calculate_cost(input_tokens, output_tokens)
        
        # Create request stats
        stats = RequestStats(
            timestamp=datetime.now(),
            model=model,
            usage=usage,
            cost=cost,
            duration_ms=duration_ms,
            prompt_preview=prompt_preview[:100] if prompt_preview else ""
        )
        
        # Update session stats
        self.session_stats.add_request(stats)
        self.request_history.append(stats)
        
        if self.verbose:
            logger.info(
                f"Request tracked: {model} - "
                f"{usage.total_tokens} tokens, ${cost:.4f}"
            )
        
        return stats
    
    def track_from_response(
        self,
        model: str,
        response: Any,
        duration_ms: float = 0.0
    ) -> Optional[RequestStats]:
        """
        Track request from LLM response object.
        
        Handles various response formats from different providers.
        """
        try:
            # Try to extract usage from response
            usage = None
            
            # OpenAI format
            if hasattr(response, 'usage'):
                usage = response.usage
                input_tokens = getattr(usage, 'prompt_tokens', 0)
                output_tokens = getattr(usage, 'completion_tokens', 0)
                cached_tokens = getattr(usage, 'cached_tokens', 0)
            # Dict format
            elif isinstance(response, dict) and 'usage' in response:
                usage = response['usage']
                input_tokens = usage.get('prompt_tokens', 0)
                output_tokens = usage.get('completion_tokens', 0)
                cached_tokens = usage.get('cached_tokens', 0)
            else:
                logger.debug("Could not extract usage from response")
                return None
            
            return self.track_request(
                model=model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cached_tokens=cached_tokens,
                duration_ms=duration_ms
            )
        except Exception as e:
            logger.error(f"Error tracking response: {e}")
            return None
    
    def get_current_stats(self) -> SessionStats:
        """Get current session statistics."""
        return self.session_stats
    
    def get_total_cost(self) -> float:
        """Get total cost for the session."""
        return self.session_stats.total_cost
    
    def get_total_tokens(self) -> int:
        """Get total tokens for the session."""
        return self.session_stats.total_tokens
    
    def get_request_count(self) -> int:
        """Get total request count."""
        return self.session_stats.total_requests
    
    def format_summary(self) -> str:
        """Format a summary of the session statistics."""
        stats = self.session_stats
        
        lines = [
            f"Session: {stats.session_id}",
            f"Duration: {stats.duration_seconds:.1f}s",
            f"Requests: {stats.total_requests}",
            "",
            "Tokens:",
            f"  Input:  {stats.total_input_tokens:,}",
            f"  Output: {stats.total_output_tokens:,}",
            f"  Total:  {stats.total_tokens:,}",
            f"  Cached: {stats.total_cached_tokens:,}",
            "",
            f"Cost: ${stats.total_cost:.4f}",
            f"Avg per request: ${stats.avg_cost_per_request:.4f}",
        ]
        
        if stats.models_used:
            lines.append("")
            lines.append("Models used:")
            for model, count in stats.models_used.items():
                lines.append(f"  {model}: {count} requests")
        
        return "\n".join(lines)
    
    def print_summary(self) -> None:
        """Print a formatted summary to console."""
        from rich.console import Console
        from rich.panel import Panel
        from rich.table import Table
        
        console = Console()
        stats = self.session_stats
        
        # Create summary table
        table = Table(show_header=True, header_style="bold cyan")
        table.add_column("Metric")
        table.add_column("Value", justify="right")
        
        table.add_row("Session ID", stats.session_id)
        table.add_row("Duration", f"{stats.duration_seconds:.1f}s")
        table.add_row("Requests", str(stats.total_requests))
        table.add_row("", "")
        table.add_row("Input Tokens", f"{stats.total_input_tokens:,}")
        table.add_row("Output Tokens", f"{stats.total_output_tokens:,}")
        table.add_row("Total Tokens", f"{stats.total_tokens:,}")
        table.add_row("Cached Tokens", f"{stats.total_cached_tokens:,}")
        table.add_row("", "")
        table.add_row("Total Cost", f"${stats.total_cost:.4f}")
        table.add_row("Avg Cost/Request", f"${stats.avg_cost_per_request:.4f}")
        
        console.print(Panel(table, title="💰 Session Statistics", border_style="green"))
        
        # Print model breakdown if multiple models used
        if len(stats.models_used) > 1:
            model_table = Table(show_header=True, header_style="bold cyan")
            model_table.add_column("Model")
            model_table.add_column("Requests", justify="right")
            
            for model, count in stats.models_used.items():
                model_table.add_row(model, str(count))
            
            console.print(Panel(model_table, title="Models Used", border_style="blue"))
    
    def export_json(self, filepath: Optional[str] = None) -> str:
        """
        Export session data to JSON.
        
        Args:
            filepath: Optional file path to write to
            
        Returns:
            JSON string
        """
        data = {
            "session": self.session_stats.to_dict(),
            "requests": [r.to_dict() for r in self.request_history]
        }
        
        json_str = json.dumps(data, indent=2)
        
        if filepath:
            with open(filepath, 'w') as f:
                f.write(json_str)
            logger.info(f"Exported session data to {filepath}")
        
        return json_str
    
    def end_session(self) -> SessionStats:
        """Mark the session as ended."""
        self.session_stats.end_time = datetime.now()
        return self.session_stats


# ============================================================================
# CLI Integration Handler
# ============================================================================

class CostTrackerHandler:
    """
    Handler for integrating cost tracking with PraisonAI CLI.
    """
    
    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self._tracker: Optional[CostTracker] = None
    
    @property
    def feature_name(self) -> str:
        return "cost_tracker"
    
    def initialize(self, session_id: Optional[str] = None) -> CostTracker:
        """Initialize the cost tracker."""
        self._tracker = CostTracker(
            session_id=session_id,
            verbose=self.verbose
        )
        
        if self.verbose:
            from rich import print as rprint
            rprint(f"[cyan]Cost tracking enabled for session: {self._tracker.session_id}[/cyan]")
        
        return self._tracker
    
    def get_tracker(self) -> Optional[CostTracker]:
        """Get the current cost tracker."""
        return self._tracker
    
    def track_request(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
        **kwargs
    ) -> Optional[RequestStats]:
        """Track a request."""
        if not self._tracker:
            self._tracker = self.initialize()
        
        return self._tracker.track_request(
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            **kwargs
        )
    
    def get_summary(self) -> Dict[str, Any]:
        """Get session summary as dict."""
        if not self._tracker:
            return {}
        return self._tracker.session_stats.to_dict()
    
    def print_summary(self) -> None:
        """Print session summary."""
        if self._tracker:
            self._tracker.print_summary()
    
    def get_cost(self) -> float:
        """Get total cost."""
        if self._tracker:
            return self._tracker.get_total_cost()
        return 0.0
    
    def get_tokens(self) -> int:
        """Get total tokens."""
        if self._tracker:
            return self._tracker.get_total_tokens()
        return 0
