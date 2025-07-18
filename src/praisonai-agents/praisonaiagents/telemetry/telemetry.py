"""
Minimal telemetry implementation for PraisonAI Agents.

This module provides anonymous usage tracking with privacy-first design.
All telemetry is opt-out via environment variables.
"""

import os
import time
import platform
import hashlib
import threading
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
    
    # Common error phrases that indicate interpreter shutdown
    _SHUTDOWN_ERROR_PHRASES = [
        'cannot schedule new futures',
        'interpreter shutdown',
        'atexit after shutdown',
        'event loop closed',
        'runtime is shutting down'
    ]
    
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
        
        # Add shutdown tracking to prevent double shutdown
        self._shutdown_complete = False
        self._shutdown_lock = threading.Lock()
        
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
        self._metrics_lock = threading.Lock()
        self._max_timing_entries = 1000  # Limit to prevent memory leaks
        
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
        except (ImportError, KeyError, AttributeError):
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
            
        with self._metrics_lock:
            self._metrics["agent_executions"] += 1
        
        # Send event to PostHog
        if self._posthog:
            self._posthog.capture(
                distinct_id=self.session_id,
                event='agent_execution',
                properties={
                    'success': success,
                    'session_id': self.session_id
                }
            )
        
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
            
        with self._metrics_lock:
            self._metrics["task_completions"] += 1
        
        # Send event to PostHog
        if self._posthog:
            self._posthog.capture(
                distinct_id=self.session_id,
                event='task_completion',
                properties={
                    'success': success,
                    'session_id': self.session_id
                }
            )
        
        self.logger.debug(f"Task completion tracked: success={success}")
    
    def track_tool_usage(self, tool_name: str, success: bool = True, execution_time: float = None):
        """
        Track tool usage event with optional timing.
        
        Args:
            tool_name: Name of the tool being used
            success: Whether the tool call was successful
            execution_time: Time in seconds the tool took to execute (optional)
        """
        if not self.enabled:
            return
            
        with self._metrics_lock:
            self._metrics["tool_calls"] += 1
            
            # Add timing metrics if provided (with memory management)
            if execution_time is not None:
                if "tool_execution_times" not in self._metrics:
                    self._metrics["tool_execution_times"] = []
                
                timing_list = self._metrics["tool_execution_times"]
                timing_list.append({
                    "tool_name": tool_name,
                    "execution_time": execution_time,
                    "success": success
                })
                
                # Prevent memory leaks by limiting stored entries
                if len(timing_list) > self._max_timing_entries:
                    timing_list[:] = timing_list[-self._max_timing_entries:]
        
        # Send event to PostHog
        if self._posthog:
            properties = {
                'tool_name': tool_name,
                'success': success,
                'session_id': self.session_id
            }
            
            # Include execution time if available
            if execution_time is not None:
                properties['execution_time'] = execution_time
            
            self._posthog.capture(
                distinct_id=self.session_id,
                event='tool_usage',
                properties=properties
            )
        
        # Only track tool name, not arguments or results
        debug_msg = f"Tool usage tracked: {tool_name}, success={success}"
        if execution_time is not None:
            debug_msg += f", execution_time={execution_time:.3f}s"
        self.logger.debug(debug_msg)
    
    def track_error(self, error_type: str = None):
        """
        Track an error event.
        
        Args:
            error_type: Type of error (not the full message)
        """
        if not self.enabled:
            return
            
        with self._metrics_lock:
            self._metrics["errors"] += 1
        
        # Send event to PostHog
        if self._posthog:
            self._posthog.capture(
                distinct_id=self.session_id,
                event='error',
                properties={
                    'error_type': error_type or 'unknown',
                    'session_id': self.session_id
                }
            )
        
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
            
        # Send event to PostHog
        if self._posthog:
            self._posthog.capture(
                distinct_id=self.session_id,
                event='feature_usage',
                properties={
                    'feature_name': feature_name,
                    'session_id': self.session_id
                }
            )
            
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
            
        with self._metrics_lock:
            metrics_copy = self._metrics.copy()
            
        return {
            "enabled": True,
            "session_id": self.session_id,
            "metrics": metrics_copy,
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
        with self._metrics_lock:
            for key in self._metrics:
                if isinstance(self._metrics[key], int):
                    self._metrics[key] = 0
    
    def shutdown(self):
        """
        Shutdown telemetry and ensure all events are sent.
        Forces proper cleanup of background threads to prevent hanging.
        """
        if not self.enabled:
            return
        
        # Use lock to prevent concurrent shutdown calls
        with self._shutdown_lock:
            if self._shutdown_complete:
                return
            self._shutdown_complete = True
            
        # Final flush
        self.flush()
        
        # Shutdown PostHog if available
        posthog_client = getattr(self, '_posthog', None)
        if posthog_client:
            try:
                # Check if Python interpreter is shutting down
                if self._is_interpreter_shutting_down():
                    self.logger.debug("Interpreter shutting down, skipping PostHog operations")
                    return
                
                # Use a timeout-based flush to prevent hanging
                import threading
                import time
                import concurrent.futures
                
                # Use ThreadPoolExecutor for better control
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                    flush_future = executor.submit(self._safe_flush_posthog, posthog_client)
                    
                    try:
                        flush_future.result(timeout=5.0)  # 5 second timeout
                        self.logger.debug("PostHog flush completed successfully")
                    except concurrent.futures.TimeoutError:
                        self.logger.warning("PostHog flush timed out")
                        flush_future.cancel()
                    except Exception as e:
                        self.logger.error(f"PostHog flush failed: {e}")
                
                # Cleanup PostHog threads safely
                self._shutdown_posthog_threads(posthog_client)
                
                # Standard shutdown - with interpreter shutdown check
                if not self._is_interpreter_shutting_down():
                    posthog_client.shutdown()
                else:
                    self.logger.debug("Skipping PostHog shutdown call due to interpreter shutdown")
                
            except Exception as e:
                # Handle specific shutdown-related errors gracefully
                if self._is_shutdown_related_error(e):
                    self.logger.debug(f"PostHog shutdown prevented due to interpreter shutdown: {e}")
                else:
                    self.logger.error(f"Error during PostHog shutdown: {e}")
            finally:
                self._posthog = None
    
    def _is_shutdown_related_error(self, error: Exception) -> bool:
        """
        Check if an error is related to interpreter shutdown.
        
        Args:
            error: The exception to check
            
        Returns:
            True if the error is shutdown-related, False otherwise
        """
        error_msg = str(error).lower()
        return any(phrase in error_msg for phrase in self._SHUTDOWN_ERROR_PHRASES)
    
    def _is_interpreter_shutting_down(self) -> bool:
        """
        Check if the Python interpreter is shutting down.
        
        Returns:
            True if interpreter is shutting down, False otherwise
        """
        try:
            import sys
            
            # Check if the interpreter is in shutdown mode
            if hasattr(sys, 'is_finalizing') and sys.is_finalizing():
                return True
            
            # Check if we can create new threads (fails during shutdown)
            try:
                test_thread = threading.Thread(target=lambda: None)
                test_thread.daemon = True
                test_thread.start()
                test_thread.join(timeout=0.001)
                return False
            except (RuntimeError, threading.ThreadError):
                return True
                
        except Exception:
            # If we can't determine state, assume we're shutting down to be safe
            return True
    
    def _safe_flush_posthog(self, posthog_client):
        """Safely flush PostHog data with error handling."""
        try:
            # Skip flush if interpreter is shutting down
            if self._is_interpreter_shutting_down():
                self.logger.debug("Skipping PostHog flush due to interpreter shutdown")
                return False
                
            posthog_client.flush()
            return True
        except Exception as e:
            if self._is_shutdown_related_error(e):
                self.logger.debug(f"PostHog flush prevented due to interpreter shutdown: {e}")
            else:
                self.logger.debug(f"PostHog flush error: {e}")
            return False
    
    def _shutdown_posthog_threads(self, posthog_client):
        """Safely shutdown PostHog background threads."""
        try:
            # Skip thread cleanup if interpreter is shutting down
            if self._is_interpreter_shutting_down():
                self.logger.debug("Skipping PostHog thread cleanup due to interpreter shutdown")
                return
                
            # Access thread pool safely (fix double shutdown issue)
            thread_pool = getattr(posthog_client, '_thread_pool', None)
            if thread_pool:
                try:
                    # Single shutdown call with timeout
                    if hasattr(thread_pool, 'shutdown'):
                        thread_pool.shutdown(wait=False)
                        # Wait briefly for graceful shutdown
                        import time
                        time.sleep(0.5)
                except Exception as e:
                    if self._is_shutdown_related_error(e):
                        self.logger.debug(f"Thread pool shutdown prevented due to interpreter shutdown: {e}")
                    else:
                        self.logger.debug(f"Thread pool shutdown error: {e}")
            
            # Clean up consumer
            consumer = getattr(posthog_client, '_consumer', None)
            if consumer:
                try:
                    if hasattr(consumer, 'flush'):
                        consumer.flush()
                    if hasattr(consumer, 'shutdown'):
                        consumer.shutdown()
                except Exception as e:
                    if self._is_shutdown_related_error(e):
                        self.logger.debug(f"Consumer shutdown prevented due to interpreter shutdown: {e}")
                    else:
                        self.logger.debug(f"Consumer shutdown error: {e}")
                    
        except Exception as e:
            if self._is_shutdown_related_error(e):
                self.logger.debug(f"PostHog thread cleanup prevented due to interpreter shutdown: {e}")
            else:
                self.logger.debug(f"Error during PostHog thread cleanup: {e}")


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


def force_shutdown_telemetry():
    """
    Force shutdown of telemetry system with comprehensive cleanup.
    This function ensures proper termination of all background threads.
    """
    global _telemetry_instance
    if _telemetry_instance:
        _telemetry_instance.shutdown()
        
        # Additional cleanup - wait for all threads to finish
        import threading
        import time
        
        # Wait up to 3 seconds for any remaining threads to finish
        max_wait = 3.0
        start_time = time.time()
        
        while time.time() - start_time < max_wait:
            # Check for any analytics/telemetry related threads
            analytics_threads = [
                t for t in threading.enumerate() 
                if t != threading.current_thread() 
                and not t.daemon
                and any(keyword in t.name.lower() for keyword in ['posthog', 'analytics', 'telemetry', 'consumer'])
            ]
            
            if not analytics_threads:
                break
                
            time.sleep(0.1)
        
        # Reset the global instance
        _telemetry_instance = None


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
        """Stop telemetry collection and properly shutdown."""
        self.telemetry.shutdown()
    
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