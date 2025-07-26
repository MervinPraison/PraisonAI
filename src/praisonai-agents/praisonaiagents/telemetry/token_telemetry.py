"""
Token telemetry integration for bridging token tracking with the main telemetry system.
"""

from typing import Optional, Dict, Any
import logging

# Import dependencies
from .token_collector import _token_collector, TokenMetrics
from .telemetry import get_telemetry

logger = logging.getLogger(__name__)


class TokenTelemetryBridge:
    """Bridges token tracking with the main telemetry system."""
    
    def __init__(self):
        self.telemetry = get_telemetry()
        self.enabled = self.telemetry.enabled if self.telemetry else False
    
    def track_token_usage(
        self, 
        event_type: str,
        model: str,
        agent: Optional[str],
        metrics: TokenMetrics,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """Track token usage event in telemetry."""
        if not self.enabled or not self.telemetry:
            return
        
        try:
            # Prepare event data
            event_data = {
                "event_type": event_type,
                "model": model,
                "agent": agent,
                "total_tokens": metrics.total_tokens,
                "input_tokens": metrics.input_tokens,
                "output_tokens": metrics.output_tokens,
                "cached_tokens": metrics.cached_tokens,
                "reasoning_tokens": metrics.reasoning_tokens,
            }
            
            # Add metadata if provided
            if metadata:
                event_data.update(metadata)
            
            # Track in telemetry
            self.telemetry.track_feature_usage("token_usage", event_data)
            
        except Exception as e:
            logger.debug(f"Failed to track token usage in telemetry: {e}")
    
    def export_token_metrics(self) -> Dict[str, Any]:
        """Export token metrics for telemetry reporting."""
        if not _token_collector:
            return {}
        
        try:
            metrics = _token_collector.export_metrics()
            
            # Prepare telemetry-friendly format
            return {
                "token_metrics": {
                    "session_summary": metrics.get("session", {}),
                    "total_interactions": metrics.get("session", {}).get("total_interactions", 0),
                    "total_tokens": metrics.get("session", {}).get("total_tokens", 0),
                }
            }
            
        except Exception as e:
            logger.debug(f"Failed to export token metrics: {e}")
            return {}
    
    def reset_token_metrics(self):
        """Reset token metrics collection."""
        if _token_collector:
            _token_collector.reset()


# Global telemetry bridge instance
_token_telemetry_bridge = TokenTelemetryBridge()

# Export convenience functions
track_token_usage = _token_telemetry_bridge.track_token_usage
export_token_metrics = _token_telemetry_bridge.export_token_metrics