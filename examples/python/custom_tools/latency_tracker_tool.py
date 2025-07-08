"""
Minimal Latency Tracking Tool for PraisonAI MCP Server

This tool provides latency tracking without modifying core files.
It uses decorators and wrapper functions to track execution times
for planning, tool usage, and LLM generation phases.
"""

import time
import json
import threading
from typing import Dict, Any, Callable, Optional
from functools import wraps
from contextlib import contextmanager


class LatencyTracker:
    """Minimal latency tracking tool for MCP server operations."""
    
    def __init__(self):
        self._data = {}
        self._lock = threading.Lock()
        self._active_timers = {}
    
    def start_timer(self, phase: str, request_id: str = "default"):
        """Start timing a phase."""
        with self._lock:
            key = f"{request_id}_{phase}"
            self._active_timers[key] = time.time()
    
    def end_timer(self, phase: str, request_id: str = "default") -> float:
        """End timing a phase and return elapsed time."""
        with self._lock:
            key = f"{request_id}_{phase}"
            if key not in self._active_timers:
                return 0.0
            
            elapsed = time.time() - self._active_timers[key]
            del self._active_timers[key]
            
            # Store the timing
            if request_id not in self._data:
                self._data[request_id] = {}
            if phase not in self._data[request_id]:
                self._data[request_id][phase] = []
            self._data[request_id][phase].append(elapsed)
            
            return elapsed
    
    @contextmanager
    def track(self, phase: str, request_id: str = "default"):
        """Context manager for tracking a phase."""
        self.start_timer(phase, request_id)
        try:
            yield
        finally:
            self.end_timer(phase, request_id)
    
    def get_metrics(self, request_id: str = "default") -> Dict[str, Any]:
        """Get metrics for a specific request."""
        with self._lock:
            if request_id not in self._data:
                return {}
            
            metrics = {}
            for phase, timings in self._data[request_id].items():
                if timings:
                    metrics[phase] = {
                        'count': len(timings),
                        'total': sum(timings),
                        'average': sum(timings) / len(timings),
                        'min': min(timings),
                        'max': max(timings),
                        'latest': timings[-1]
                    }
            return metrics
    
    def get_summary(self) -> Dict[str, Any]:
        """Get summary of all tracked requests."""
        with self._lock:
            summary = {}
            for request_id, phases in self._data.items():
                summary[request_id] = self.get_metrics(request_id)
            return summary
    
    def clear(self, request_id: Optional[str] = None):
        """Clear tracking data."""
        with self._lock:
            if request_id:
                self._data.pop(request_id, None)
            else:
                self._data.clear()
            self._active_timers.clear()


# Global tracker instance
tracker = LatencyTracker()


def track_latency(phase: str, request_id: str = "default"):
    """Decorator to track function execution latency."""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            with tracker.track(phase, request_id):
                return func(*args, **kwargs)
        return wrapper
    return decorator


def create_tracked_agent(agent_class):
    """Create a wrapper class that tracks agent operations."""
    class TrackedAgent(agent_class):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self._request_id = kwargs.get('request_id', 'default')
        
        def chat(self, *args, **kwargs):
            """Tracked chat method for planning phase."""
            with tracker.track('planning', self._request_id):
                return super().chat(*args, **kwargs)
        
        def execute_tool(self, *args, **kwargs):
            """Tracked execute_tool method."""
            with tracker.track('tool_usage', self._request_id):
                return super().execute_tool(*args, **kwargs)
    
    return TrackedAgent


def create_tracked_llm(llm_class):
    """Create a wrapper class that tracks LLM operations."""
    class TrackedLLM(llm_class):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self._request_id = kwargs.get('request_id', 'default')
        
        def get_response(self, *args, **kwargs):
            """Tracked get_response method for LLM generation."""
            with tracker.track('llm_generation', self._request_id):
                return super().get_response(*args, **kwargs)
    
    return TrackedLLM


# Custom tool function for manual tracking
def latency_tracking_tool(action: str, phase: str = "", request_id: str = "default") -> str:
    """
    Manual latency tracking tool for PraisonAI agents.
    
    Args:
        action: One of 'start', 'end', 'metrics', 'summary', 'clear'
        phase: Phase name (for 'start' and 'end' actions)
        request_id: Request identifier for tracking
    
    Returns:
        str: JSON string with results
    """
    if action == "start":
        if not phase:
            return json.dumps({"error": "Phase name required for start action"})
        tracker.start_timer(phase, request_id)
        return json.dumps({"status": "started", "phase": phase, "request_id": request_id})
    
    elif action == "end":
        if not phase:
            return json.dumps({"error": "Phase name required for end action"})
        elapsed = tracker.end_timer(phase, request_id)
        return json.dumps({
            "status": "ended", 
            "phase": phase, 
            "request_id": request_id,
            "elapsed": elapsed
        })
    
    elif action == "metrics":
        metrics = tracker.get_metrics(request_id)
        return json.dumps({"request_id": request_id, "metrics": metrics})
    
    elif action == "summary":
        summary = tracker.get_summary()
        return json.dumps({"summary": summary})
    
    elif action == "clear":
        tracker.clear(request_id)
        return json.dumps({"status": "cleared", "request_id": request_id})
    
    else:
        return json.dumps({"error": f"Unknown action: {action}"})


# Convenience functions for external use
def start_tracking(phase: str, request_id: str = "default"):
    """Start tracking a phase."""
    tracker.start_timer(phase, request_id)


def end_tracking(phase: str, request_id: str = "default") -> float:
    """End tracking a phase and return elapsed time."""
    return tracker.end_timer(phase, request_id)


def get_latency_metrics(request_id: str = "default") -> Dict[str, Any]:
    """Get latency metrics for a request."""
    return tracker.get_metrics(request_id)


def get_latency_summary() -> Dict[str, Any]:
    """Get summary of all latency tracking."""
    return tracker.get_summary()