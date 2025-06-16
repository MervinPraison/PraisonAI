"""
Minimal telemetry implementation for PraisonAI Agents.

This module provides anonymous usage tracking with privacy-first design.
All telemetry is opt-out via environment variables.
"""

import os
import time
import platform
import hashlib
from typing import Dict, Any, Optional
from datetime import datetime
import logging

# Try to import PostHog
try:
    from posthog import Posthog
    POSTHOG_AVAILABLE = True
except ImportError:
    POSTHOG_AVAILABLE = False

# Check for opt-out environment variables
_TELEMETRY_DISABLED = any([
    os.environ.get('PRAISONAI_TELEMETRY_DISABLED', '').lower() in ('true', '1', 'yes'),
    os.environ.get('PRAISONAI_DISABLE_TELEMETRY', '').lower() in ('true', '1', 'yes'),
    os.environ.get('DO_NOT_TRACK', '').lower() in ('true', '1', 'yes'),
])


class MinimalTelemetry:
    """
    Minimal telemetry collector for anonymous usage tracking.
    
    Privacy guarantees:
    - No personal data is collected
    - No prompts, responses, or user content is tracked
    - Only anonymous metrics about feature usage
    - Respects DO_NOT_TRACK standard
    - Can be disabled via environment variables
    """
    
    def __init__(self, enabled: bool = None):
        """
        Initialize the minimal telemetry collector.
        
        Args:
            enabled: Override the environment-based enable/disable setting
        """
        # Respect explicit enabled parameter, otherwise check environment
        if enabled is not None:
            self.enabled = enabled
        else:
            self.enabled = not _TELEMETRY_DISABLED
            
        self.logger = logging.getLogger(__name__)
        
        if not self.enabled:
            self.logger.debug("Telemetry is disabled")
            return
            
        # Generate anonymous session ID (not user ID)
        session_data = f"{datetime.now().isoformat()}-{os.getpid()}-{time.time()}"
        self.session_id = hashlib.sha256(session_data.encode()).hexdigest()[:16]
        
        # Basic metrics storage
        self._metrics = {
            "agent_executions": 0,
            "task_completions": 0,
            "tool_calls": 0,
            "errors": 0,
        }
        
        # Collect basic environment info (anonymous)
        self._environment = {
            "python_version": platform.python_version(),
            "os_type": platform.system(),
            "framework_version": self._get_framework_version(),
        }
        
        self.logger.debug(f"Telemetry enabled with session {self.session_id}")
        
        # Initialize PostHog if available
        if POSTHOG_AVAILABLE:
            try:
                self._posthog = Posthog(
                    project_api_key='phc_skZpl3eFLQJ4iYjsERNMbCO6jfeSJi2vyZlPahKgxZ7',
                    host='https://eu.i.posthog.com',
                    disable_geoip=True,
                    on_error=lambda e: self.logger.debug(f"PostHog error: {e}"),
                    sync_mode=False  # Use async mode to prevent blocking
                )
            except:
                self._posthog = None
        else:
            self._posthog = None
    
    def _get_framework_version(self) -> str:
        """Get the PraisonAI Agents version."""
        try:
            from .. import __version__
            return __version__
        except ImportError:
            return "unknown"
    
    def track_agent_execution(self, agent_name: str = None, success: bool = True):
        """
        Track an agent execution event.
        
        Args:
            agent_name: Name of the agent (not logged, just for counting)
            success: Whether the execution was successful
        """
        if not self.enabled:
            return
            
        self._metrics["agent_executions"] += 1
        
        # In a real implementation, this would send to a backend
        # For now, just log at debug level
        self.logger.debug(f"Agent execution tracked: success={success}")
    
    def track_task_completion(self, task_name: str = None, success: bool = True):
        """
        Track a task completion event.
        
        Args:
            task_name: Name of the task (not logged, just for counting)
            success: Whether the task completed successfully
        """
        if not self.enabled:
            return
            
        self._metrics["task_completions"] += 1
        
        self.logger.debug(f"Task completion tracked: success={success}")
    
    def track_tool_usage(self, tool_name: str, success: bool = True):
        """
        Track tool usage event.
        
        Args:
            tool_name: Name of the tool being used
            success: Whether the tool call was successful
        """
        if not self.enabled:
            return
            
        self._metrics["tool_calls"] += 1
        
        # Only track tool name, not arguments or results
        self.logger.debug(f"Tool usage tracked: {tool_name}, success={success}")
    
    def track_error(self, error_type: str = None):
        """
        Track an error event.
        
        Args:
            error_type: Type of error (not the full message)
        """
        if not self.enabled:
            return
            
        self._metrics["errors"] += 1
        
        # Only track error type, not full error messages
        self.logger.debug(f"Error tracked: type={error_type or 'unknown'}")
    
    def track_feature_usage(self, feature_name: str):
        """
        Track usage of a specific feature.
        
        Args:
            feature_name: Name of the feature being used
        """
        if not self.enabled:
            return
            
        # Track which features are being used
        self.logger.debug(f"Feature usage tracked: {feature_name}")
    
    def get_metrics(self) -> Dict[str, Any]:
        """
        Get current metrics summary.
        
        Returns:
            Dictionary of current metrics
        """
        if not self.enabled:
            return {"enabled": False}
            
        return {
            "enabled": True,
            "session_id": self.session_id,
            "metrics": self._metrics.copy(),
            "environment": self._environment.copy(),
        }
    
    def flush(self):
        """
        Flush any pending telemetry data.
        
        In a real implementation, this would send data to a backend.
        """
        if not self.enabled:
            return
            
        metrics = self.get_metrics()
        self.logger.debug(f"Telemetry flush: {metrics}")
        
        # Send to PostHog if available
        if hasattr(self, '_posthog') and self._posthog:
            
            try:
                self._posthog.capture(
                    distinct_id='anonymous',
                    event='sdk_used',
                    properties={
                        'version': self._environment['framework_version'],
                        'os': platform.system(),
                        '$process_person_profile': False,
                        '$geoip_disable': True
                    }
                )
                # Don't flush here - let PostHog handle it asynchronously
            except:
                pass
        
        # Reset counters
        for key in self._metrics:
            if isinstance(self._metrics[key], int):
                self._metrics[key] = 0
    
    def shutdown(self):
        """
        Shutdown telemetry and ensure all events are sent.
        """
        if not self.enabled:
            return
            
        # Final flush
        self.flush()
        
        # Shutdown PostHog if available
        if hasattr(self, '_posthog') and self._posthog:
            try:
                # Force a synchronous flush before shutdown
                self._posthog.flush()
                self._posthog.shutdown()
            except:
                pass


# Global telemetry instance
_telemetry_instance = None


def get_telemetry() -> MinimalTelemetry:
    """
    Get the global telemetry instance.
    
    Returns:
        The global MinimalTelemetry instance
    """
    global _telemetry_instance
    if _telemetry_instance is None:
        _telemetry_instance = MinimalTelemetry()
    return _telemetry_instance


def disable_telemetry():
    """Programmatically disable telemetry."""
    global _telemetry_instance
    if _telemetry_instance:
        _telemetry_instance.enabled = False
    else:
        _telemetry_instance = MinimalTelemetry(enabled=False)


def enable_telemetry():
    """Programmatically enable telemetry (if not disabled by environment)."""
    global _telemetry_instance
    if not _TELEMETRY_DISABLED:
        if _telemetry_instance:
            _telemetry_instance.enabled = True
        else:
            _telemetry_instance = MinimalTelemetry(enabled=True)


# For backward compatibility with existing code
class TelemetryCollector:
    """Backward compatibility wrapper for the old TelemetryCollector interface."""
    
    def __init__(self, backend: str = "minimal", service_name: str = "praisonai-agents", **kwargs):
        self.telemetry = get_telemetry()
        
    def start(self):
        """Start telemetry collection."""
        # No-op for minimal implementation
        pass
        
    def stop(self):
        """Stop telemetry collection and flush data."""
        self.telemetry.flush()
    
    def trace_agent_execution(self, agent_name: str, **attributes):
        """Compatibility method for agent execution tracking."""
        from contextlib import contextmanager
        
        @contextmanager
        def _trace():
            try:
                yield None
                self.telemetry.track_agent_execution(agent_name, success=True)
            except Exception:
                self.telemetry.track_agent_execution(agent_name, success=False)
                raise
                
        return _trace()
    
    def trace_task_execution(self, task_name: str, agent_name: str = None, **attributes):
        """Compatibility method for task execution tracking."""
        from contextlib import contextmanager
        
        @contextmanager
        def _trace():
            try:
                yield None
                self.telemetry.track_task_completion(task_name, success=True)
            except Exception:
                self.telemetry.track_task_completion(task_name, success=False)
                raise
                
        return _trace()
    
    def trace_tool_call(self, tool_name: str, **attributes):
        """Compatibility method for tool call tracking."""
        from contextlib import contextmanager
        
        @contextmanager
        def _trace():
            try:
                yield None
                self.telemetry.track_tool_usage(tool_name, success=True)
            except Exception:
                self.telemetry.track_tool_usage(tool_name, success=False)
                raise
                
        return _trace()
    
    def trace_llm_call(self, model: str = None, **attributes):
        """Compatibility method for LLM call tracking."""
        from contextlib import contextmanager
        
        @contextmanager
        def _trace():
            # We don't track LLM calls in minimal telemetry
            yield None
            
        return _trace()
    
    def record_tokens(self, prompt_tokens: int, completion_tokens: int, model: str = None):
        """Compatibility method - we don't track token usage."""
        pass
        
    def record_cost(self, cost: float, model: str = None):
        """Compatibility method - we don't track costs."""
        pass
        
    def get_metrics(self) -> Dict[str, Any]:
        """Get current metrics."""
        return self.telemetry.get_metrics()