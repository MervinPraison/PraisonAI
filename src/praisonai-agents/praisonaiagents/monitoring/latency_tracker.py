import time
import threading
from typing import Dict, List, Optional, Any
from contextlib import contextmanager
from functools import wraps
import os
import json


class LatencyTracker:
    """
    Minimal latency tracking for MCP server phases.
    
    Tracks timing for:
    - Planning phase (agent prompt processing)
    - Tool usage phase (tool execution)
    - LLM generation phase (LLM API calls)
    """
    
    def __init__(self):
        self._data = threading.local()
        self._metrics: Dict[str, List[float]] = {
            "planning": [],
            "tool_usage": [],
            "llm_generation": [],
            "total": []
        }
        self._current_request: Dict[str, Any] = {}
        self._lock = threading.Lock()
        self._enabled = os.getenv("PRAISON_LATENCY_TRACKING", "false").lower() == "true"
    
    @property
    def enabled(self) -> bool:
        """Check if latency tracking is enabled."""
        return self._enabled
    
    def enable(self):
        """Enable latency tracking."""
        self._enabled = True
    
    def disable(self):
        """Disable latency tracking."""
        self._enabled = False
    
    @contextmanager
    def track_phase(self, phase: str):
        """Context manager to track timing for a specific phase."""
        if not self._enabled:
            yield
            return
            
        start_time = time.time()
        
        # Initialize thread-local data if needed
        if not hasattr(self._data, 'current_timings'):
            self._data.current_timings = {}
        
        try:
            yield
        finally:
            elapsed = time.time() - start_time
            
            # Store timing in thread-local storage
            if phase not in self._data.current_timings:
                self._data.current_timings[phase] = []
            self._data.current_timings[phase].append(elapsed)
            
            # Also store in global metrics for reporting
            with self._lock:
                if phase not in self._metrics:
                    self._metrics[phase] = []
                self._metrics[phase].append(elapsed)
    
    def track_function(self, phase: str):
        """Decorator to track timing for a function."""
        def decorator(func):
            @wraps(func)
            def wrapper(*args, **kwargs):
                if not self._enabled:
                    return func(*args, **kwargs)
                    
                with self.track_phase(phase):
                    return func(*args, **kwargs)
            
            @wraps(func)
            async def async_wrapper(*args, **kwargs):
                if not self._enabled:
                    return await func(*args, **kwargs)
                    
                with self.track_phase(phase):
                    return await func(*args, **kwargs)
            
            # Return appropriate wrapper based on function type
            if hasattr(func, '__aiter__') or hasattr(func, '__await__'):
                return async_wrapper
            return wrapper
        return decorator
    
    def start_request(self, request_id: Optional[str] = None):
        """Start tracking a new request."""
        if not self._enabled:
            return
            
        # Clear thread-local data
        self._data.current_timings = {}
        self._data.request_start = time.time()
        self._data.request_id = request_id or str(time.time())
    
    def end_request(self) -> Dict[str, Any]:
        """End request tracking and return metrics."""
        if not self._enabled:
            return {}
            
        if not hasattr(self._data, 'request_start'):
            return {}
            
        total_time = time.time() - self._data.request_start
        
        # Aggregate timings from thread-local storage
        timings = getattr(self._data, 'current_timings', {})
        
        result = {
            "request_id": getattr(self._data, 'request_id', 'unknown'),
            "total_time": total_time,
            "phases": {}
        }
        
        # Calculate phase totals
        for phase, times in timings.items():
            if times:
                result["phases"][phase] = {
                    "total": sum(times),
                    "count": len(times),
                    "average": sum(times) / len(times),
                    "times": times
                }
        
        # Store total time
        with self._lock:
            self._metrics["total"].append(total_time)
        
        return result
    
    def get_summary(self) -> Dict[str, Any]:
        """Get summary of all tracked metrics."""
        if not self._enabled:
            return {"enabled": False}
            
        with self._lock:
            summary = {"enabled": True, "phases": {}}
            
            for phase, times in self._metrics.items():
                if times:
                    summary["phases"][phase] = {
                        "total_requests": len(times),
                        "total_time": sum(times),
                        "average_time": sum(times) / len(times),
                        "min_time": min(times),
                        "max_time": max(times)
                    }
            
            return summary
    
    def clear(self):
        """Clear all tracked metrics."""
        with self._lock:
            self._metrics = {
                "planning": [],
                "tool_usage": [],
                "llm_generation": [],
                "total": []
            }
    
    def export_metrics(self, filepath: Optional[str] = None) -> str:
        """Export metrics to JSON file or return as string."""
        summary = self.get_summary()
        
        if filepath:
            with open(filepath, 'w') as f:
                json.dump(summary, f, indent=2)
            return f"Metrics exported to {filepath}"
        else:
            return json.dumps(summary, indent=2)


# Global instance for easy access
_tracker = LatencyTracker()

# Convenience functions
def track_phase(phase: str):
    """Context manager to track a phase."""
    return _tracker.track_phase(phase)

def track_function(phase: str):
    """Decorator to track a function."""
    return _tracker.track_function(phase)

def start_request(request_id: Optional[str] = None):
    """Start tracking a request."""
    _tracker.start_request(request_id)

def end_request() -> Dict[str, Any]:
    """End request tracking."""
    return _tracker.end_request()

def get_latency_summary() -> Dict[str, Any]:
    """Get latency summary."""
    return _tracker.get_summary()

def enable_tracking():
    """Enable latency tracking."""
    _tracker.enable()

def disable_tracking():
    """Disable latency tracking."""
    _tracker.disable()

def is_tracking_enabled() -> bool:
    """Check if tracking is enabled."""
    return _tracker.enabled