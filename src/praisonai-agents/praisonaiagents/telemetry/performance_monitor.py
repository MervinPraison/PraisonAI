"""
User-Friendly Performance Monitoring for PraisonAI

This module provides easy-to-use tools for monitoring function performance,
analyzing execution flow, and tracking API calls. Built on top of the existing
comprehensive telemetry infrastructure.

Features:
- Function performance evaluation with timing and statistics
- Function flow analysis and visualization
- API call tracking and performance monitoring
- Real-time performance reporting
- Easy integration with existing agents and workflows
"""

import os
import time
import json
import threading
import functools
from collections import defaultdict, deque
from typing import Dict, Any, List, Optional, Callable, Union
from contextlib import contextmanager
from datetime import datetime
import logging

try:
    from .telemetry import MinimalTelemetry
    TELEMETRY_AVAILABLE = True
except ImportError:
    TELEMETRY_AVAILABLE = False

logger = logging.getLogger(__name__)



class PerformanceMonitor:
    """
    User-friendly performance monitoring for functions, API calls, and workflows.
    
    Provides comprehensive performance tracking with simple APIs for:
    - Function execution timing and statistics
    - API call performance monitoring  
    - Function flow analysis
    - Real-time performance reporting
    """
    
    def __init__(self, max_entries: int = 10000):
        """
        Initialize the performance monitor.
        
        Args:
            max_entries: Maximum number of performance entries to keep in memory
        """
        # Check if performance monitoring is disabled
        from .telemetry import _is_monitoring_disabled
        self._monitoring_disabled = _is_monitoring_disabled()
        
        # If monitoring is disabled, use minimal initialization
        if self._monitoring_disabled:
            self.max_entries = 0
            self._lock = None
            self._function_stats = {}
            self._api_calls = {}
            self._function_flow = []
            self._active_calls = {}
            self._telemetry = None
            return
        self.max_entries = max_entries
        self._lock = threading.RLock()
        
        # Performance data storage
        self._function_stats = defaultdict(lambda: {
            'call_count': 0,
            'total_time': 0.0,
            'min_time': float('inf'),
            'max_time': 0.0,
            'recent_times': deque(maxlen=100),
            'error_count': 0,
            'last_called': None
        })
        
        self._api_calls = defaultdict(lambda: {
            'call_count': 0,
            'total_time': 0.0,
            'min_time': float('inf'),
            'max_time': 0.0,
            'success_count': 0,
            'error_count': 0,
            'recent_calls': deque(maxlen=50)
        })
        
        self._function_flow = deque(maxlen=self.max_entries)
        self._active_calls = {}
        
        # Integration with existing telemetry
        self._telemetry = None
        if TELEMETRY_AVAILABLE:
            try:
                self._telemetry = MinimalTelemetry()
            except Exception as e:
                logger.debug(f"Could not initialize telemetry integration: {e}")
    
    def monitor_function(self, func_name: Optional[str] = None):
        """
        Decorator to monitor function performance.
        
        Args:
            func_name: Optional custom name for the function
            
        Example:
            @performance_monitor.monitor_function("my_critical_function")
            def my_function():
                return "result"
        """
        # If monitoring is disabled, return unmodified function
        if self._monitoring_disabled:
            def decorator(func: Callable) -> Callable:
                return func
            return decorator
        
        def decorator(func: Callable) -> Callable:
            name = func_name or f"{func.__module__}.{func.__qualname__}"
            
            @functools.wraps(func)
            def wrapper(*args, **kwargs):
                start_time = time.time()
                thread_id = threading.get_ident()
                call_id = f"{name}_{thread_id}_{start_time}"
                
                # Track active call
                with self._lock:
                    self._active_calls[call_id] = {
                        'function': name,
                        'start_time': start_time,
                        'thread_id': thread_id
                    }
                    
                    # Add to function flow
                    self._function_flow.append({
                        'function': name,
                        'timestamp': datetime.now(),
                        'event': 'start',
                        'thread_id': thread_id
                    })
                
                try:
                    result = func(*args, **kwargs)
                    success = True
                    error = None
                except Exception as e:
                    success = False
                    error = str(e)
                    raise
                finally:
                    end_time = time.time()
                    execution_time = end_time - start_time
                    
                    # Update performance statistics
                    self._record_function_performance(name, execution_time, success, error)
                    
                    # Clean up active call
                    with self._lock:
                        self._active_calls.pop(call_id, None)
                        
                        # Add to function flow
                        self._function_flow.append({
                            'function': name,
                            'timestamp': datetime.now(),
                            'event': 'end',
                            'duration': execution_time,
                            'success': success,
                            'thread_id': thread_id
                        })
                        
                
                return result
            
            return wrapper
        return decorator
    
    @contextmanager
    def track_api_call(self, api_name: str, endpoint: Optional[str] = None):
        """
        Context manager to track API call performance.
        
        Args:
            api_name: Name of the API (e.g., "openai", "anthropic")
            endpoint: Optional specific endpoint
            
        Example:
            with performance_monitor.track_api_call("openai", "/v1/chat/completions"):
                response = openai_client.chat.completions.create(...)
        """
        # If monitoring is disabled, provide no-op context manager
        if self._monitoring_disabled:
            yield
            return
        call_name = f"{api_name}:{endpoint}" if endpoint else api_name
        start_time = time.time()
        
        try:
            yield
            success = True
            error = None
        except Exception as e:
            success = False
            error = str(e)
            raise
        finally:
            end_time = time.time()
            execution_time = end_time - start_time
            self._record_api_call(call_name, execution_time, success, error)
    
    def _record_function_performance(self, func_name: str, execution_time: float, 
                                   success: bool, error: Optional[str] = None):
        """Record function performance statistics."""
        if self._monitoring_disabled:
            return
            
        with self._lock:
            stats = self._function_stats[func_name]
            stats['call_count'] += 1
            stats['total_time'] += execution_time
            stats['min_time'] = min(stats['min_time'], execution_time)
            stats['max_time'] = max(stats['max_time'], execution_time)
            stats['recent_times'].append(execution_time)
            stats['last_called'] = datetime.now()
            
            if not success:
                stats['error_count'] += 1
            
            # Integrate with existing telemetry
            if self._telemetry:
                self._telemetry.track_tool_usage(
                    tool_name=func_name,
                    success=success,
                    execution_time=execution_time
                )
    
    def _record_api_call(self, api_name: str, execution_time: float,
                        success: bool, error: Optional[str] = None):
        """Record API call performance statistics."""
        if self._monitoring_disabled:
            return
            
        with self._lock:
            stats = self._api_calls[api_name]
            stats['call_count'] += 1
            stats['total_time'] += execution_time
            stats['min_time'] = min(stats['min_time'], execution_time)
            stats['max_time'] = max(stats['max_time'], execution_time)
            
            if success:
                stats['success_count'] += 1
            else:
                stats['error_count'] += 1
            
            stats['recent_calls'].append({
                'timestamp': datetime.now(),
                'duration': execution_time,
                'success': success,
                'error': error
            })
    
    def get_function_performance(self, func_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Get performance statistics for functions.
        
        Args:
            func_name: Specific function name, or None for all functions
            
        Returns:
            Dictionary with performance statistics
        """
        # If monitoring is disabled, return empty results
        if self._monitoring_disabled:
            return {}
            
        with self._lock:
            if func_name:
                if func_name not in self._function_stats:
                    return {}
                
                stats = self._function_stats[func_name].copy()
                # Convert deque to list for JSON serialization
                stats['recent_times'] = list(stats['recent_times'])
                
                # Calculate derived statistics
                if stats['call_count'] > 0:
                    stats['average_time'] = stats['total_time'] / stats['call_count']
                    stats['success_rate'] = (stats['call_count'] - stats['error_count']) / stats['call_count']
                    
                    if stats['recent_times']:
                        stats['recent_average'] = sum(stats['recent_times']) / len(stats['recent_times'])
                
                return {func_name: stats}
            else:
                # Return all function statistics
                result = {}
                for name, stats in self._function_stats.items():
                    processed_stats = stats.copy()
                    processed_stats['recent_times'] = list(processed_stats['recent_times'])
                    
                    if processed_stats['call_count'] > 0:
                        processed_stats['average_time'] = processed_stats['total_time'] / processed_stats['call_count']
                        processed_stats['success_rate'] = (processed_stats['call_count'] - processed_stats['error_count']) / processed_stats['call_count']
                        
                        if processed_stats['recent_times']:
                            processed_stats['recent_average'] = sum(processed_stats['recent_times']) / len(processed_stats['recent_times'])
                    
                    result[name] = processed_stats
                
                return result
    
    def get_api_call_performance(self, api_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Get performance statistics for API calls.
        
        Args:
            api_name: Specific API name, or None for all APIs
            
        Returns:
            Dictionary with API call performance statistics
        """
        # If monitoring is disabled, return empty results
        if self._monitoring_disabled:
            return {}
            
        with self._lock:
            if api_name:
                if api_name not in self._api_calls:
                    return {}
                
                stats = self._api_calls[api_name].copy()
                # Convert deque to list for JSON serialization
                recent_calls = []
                for call in stats['recent_calls']:
                    call_copy = call.copy()
                    call_copy['timestamp'] = call_copy['timestamp'].isoformat()
                    recent_calls.append(call_copy)
                stats['recent_calls'] = recent_calls
                
                # Calculate derived statistics
                if stats['call_count'] > 0:
                    stats['average_time'] = stats['total_time'] / stats['call_count']
                    stats['success_rate'] = stats['success_count'] / stats['call_count']
                    stats['error_rate'] = stats['error_count'] / stats['call_count']
                
                return {api_name: stats}
            else:
                # Return all API statistics
                result = {}
                for name, stats in self._api_calls.items():
                    processed_stats = stats.copy()
                    
                    # Convert recent calls
                    recent_calls = []
                    for call in processed_stats['recent_calls']:
                        call_copy = call.copy()
                        call_copy['timestamp'] = call_copy['timestamp'].isoformat()
                        recent_calls.append(call_copy)
                    processed_stats['recent_calls'] = recent_calls
                    
                    if processed_stats['call_count'] > 0:
                        processed_stats['average_time'] = processed_stats['total_time'] / processed_stats['call_count']
                        processed_stats['success_rate'] = processed_stats['success_count'] / processed_stats['call_count']
                        processed_stats['error_rate'] = processed_stats['error_count'] / processed_stats['call_count']
                    
                    result[name] = processed_stats
                
                return result
    
    def get_function_flow(self, last_n: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Get function execution flow information.
        
        Args:
            last_n: Number of recent flow events to return, or None for all
            
        Returns:
            List of flow events showing function execution order and timing
        """
        # If monitoring is disabled, return empty results
        if self._monitoring_disabled:
            return []
            
        with self._lock:
            flow = []
            for event in self._function_flow.copy():
                # Create a copy of the event to avoid modifying original
                event_copy = event.copy()
                # Convert timestamp to ISO format if it's a datetime object
                timestamp = event_copy['timestamp']
                if hasattr(timestamp, 'isoformat'):
                    event_copy['timestamp'] = timestamp.isoformat()
                elif not isinstance(timestamp, str):
                    event_copy['timestamp'] = str(timestamp)
                flow.append(event_copy)
            
            if last_n:
                return flow[-last_n:]
            return flow
    
    def get_active_calls(self) -> Dict[str, Any]:
        """Get information about currently executing functions."""
        # If monitoring is disabled, return empty results
        if self._monitoring_disabled:
            return {}
            
        with self._lock:
            active = {}
            current_time = time.time()
            
            for call_id, info in self._active_calls.items():
                duration = current_time - info['start_time']
                active[call_id] = {
                    'function': info['function'],
                    'duration': duration,
                    'thread_id': info['thread_id'],
                    'started_at': datetime.fromtimestamp(info['start_time']).isoformat()
                }
            
            return active
    
    def get_slowest_functions(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get the slowest performing functions."""
        # If monitoring is disabled, return empty results
        if self._monitoring_disabled:
            return []
            
        with self._lock:
            functions = []
            for name, stats in self._function_stats.items():
                if stats['call_count'] > 0:
                    avg_time = stats['total_time'] / stats['call_count']
                    functions.append({
                        'function': name,
                        'average_time': avg_time,
                        'max_time': stats['max_time'],
                        'call_count': stats['call_count']
                    })
            
            # Sort by average time descending
            functions.sort(key=lambda x: x['average_time'], reverse=True)
            return functions[:limit]
    
    def get_slowest_api_calls(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get the slowest performing API calls."""
        # If monitoring is disabled, return empty results
        if self._monitoring_disabled:
            return []
            
        with self._lock:
            apis = []
            for name, stats in self._api_calls.items():
                if stats['call_count'] > 0:
                    avg_time = stats['total_time'] / stats['call_count']
                    apis.append({
                        'api': name,
                        'average_time': avg_time,
                        'max_time': stats['max_time'],
                        'call_count': stats['call_count'],
                        'success_rate': stats['success_count'] / stats['call_count']
                    })
            
            # Sort by average time descending
            apis.sort(key=lambda x: x['average_time'], reverse=True)
            return apis[:limit]
    
    def generate_performance_report(self) -> str:
        """
        Generate a comprehensive performance report.
        
        Returns:
            Formatted string with performance analysis
        """
        report = []
        report.append("=" * 80)
        report.append("PRAISONAI PERFORMANCE MONITORING REPORT")
        report.append("=" * 80)
        report.append(f"Generated at: {datetime.now().isoformat()}")
        report.append("")
        
        # Function performance summary
        func_stats = self.get_function_performance()
        if func_stats:
            report.append("📊 FUNCTION PERFORMANCE SUMMARY")
            report.append("-" * 40)
            total_functions = len(func_stats)
            total_calls = sum(stats['call_count'] for stats in func_stats.values())
            total_errors = sum(stats['error_count'] for stats in func_stats.values())
            
            report.append(f"Total Functions Monitored: {total_functions}")
            report.append(f"Total Function Calls: {total_calls}")
            report.append(f"Total Errors: {total_errors}")
            report.append(f"Overall Success Rate: {((total_calls - total_errors) / total_calls * 100):.1f}%" if total_calls > 0 else "N/A")
            report.append("")
            
            # Slowest functions
            slowest = self.get_slowest_functions(5)
            if slowest:
                report.append("🐌 SLOWEST FUNCTIONS (Top 5)")
                for i, func in enumerate(slowest, 1):
                    report.append(f"{i}. {func['function']}")
                    report.append(f"   Average: {func['average_time']:.3f}s | Max: {func['max_time']:.3f}s | Calls: {func['call_count']}")
                report.append("")
        
        # API performance summary  
        api_stats = self.get_api_call_performance()
        if api_stats:
            report.append("🌐 API CALL PERFORMANCE SUMMARY")
            report.append("-" * 40)
            total_apis = len(api_stats)
            total_api_calls = sum(stats['call_count'] for stats in api_stats.values())
            total_api_errors = sum(stats['error_count'] for stats in api_stats.values())
            
            report.append(f"Total APIs Monitored: {total_apis}")
            report.append(f"Total API Calls: {total_api_calls}")
            report.append(f"Total API Errors: {total_api_errors}")
            report.append(f"Overall API Success Rate: {((total_api_calls - total_api_errors) / total_api_calls * 100):.1f}%" if total_api_calls > 0 else "N/A")
            report.append("")
            
            # Slowest APIs
            slowest_apis = self.get_slowest_api_calls(5)
            if slowest_apis:
                report.append("🐌 SLOWEST API CALLS (Top 5)")
                for i, api in enumerate(slowest_apis, 1):
                    report.append(f"{i}. {api['api']}")
                    report.append(f"   Average: {api['average_time']:.3f}s | Max: {api['max_time']:.3f}s | Success Rate: {api['success_rate']*100:.1f}%")
                report.append("")
        
        # Active calls
        active = self.get_active_calls()
        if active:
            report.append("⚡ CURRENTLY ACTIVE FUNCTION CALLS")
            report.append("-" * 40)
            for _call_id, info in active.items():
                report.append(f"• {info['function']} (running {info['duration']:.1f}s)")
            report.append("")
        
        # Function flow summary
        flow = self.get_function_flow(10)
        if flow:
            report.append("🔄 RECENT FUNCTION FLOW (Last 10 Events)")
            report.append("-" * 40)
            for event in flow:
                event_type = "🟢 START" if event['event'] == 'start' else "🔴 END"
                duration_info = f" ({event.get('duration', 0):.3f}s)" if event['event'] == 'end' else ""
                report.append(f"{event_type} {event['function']}{duration_info}")
            report.append("")
        
        report.append("=" * 80)
        return "\n".join(report)
    
    def clear_statistics(self):
        """Clear all performance statistics."""
        # If monitoring is disabled, nothing to clear
        if self._monitoring_disabled:
            return
            
        with self._lock:
            self._function_stats.clear()
            self._api_calls.clear()
            self._function_flow.clear()
            self._active_calls.clear()
    
    def export_data(self, format: str = "json") -> Union[str, Dict[str, Any]]:
        """
        Export all performance data.
        
        Args:
            format: Export format ("json" or "dict")
            
        Returns:
            Performance data in requested format
        """
        if self._monitoring_disabled:
            return {} if format == "dict" else "{}"
            
        data = {
            'functions': self.get_function_performance(),
            'api_calls': self.get_api_call_performance(),
            'flow': self.get_function_flow(),
            'active_calls': self.get_active_calls(),
            'export_timestamp': datetime.now().isoformat()
        }
        
        if format == "json":
            return json.dumps(data, indent=2)
        return data
    
    def export_metrics_for_external_apm(self, service_name: str = "praisonai-agents") -> Dict[str, Any]:
        """
        Export lightweight metrics suitable for external APM tools like DataDog or New Relic.
        
        This method provides a minimal overhead way to export key performance metrics
        without the expensive flow analysis operations.
        
        Args:
            service_name: Name of the service for APM tagging
            
        Returns:
            Dictionary with lightweight metrics suitable for external monitoring
        """
        if self._monitoring_disabled:
            return {}
            
        timestamp = datetime.now().isoformat()
        metrics = []
        
        # Function performance metrics (lightweight)
        for func_name, stats in self._function_stats.items():
            if stats['call_count'] > 0:
                avg_duration = stats['total_time'] / stats['call_count']
                error_rate = stats['error_count'] / stats['call_count']
                
                # Create metrics in a format suitable for external APM
                metrics.append({
                    'metric_name': 'function.execution.duration',
                    'metric_type': 'gauge',
                    'value': avg_duration,
                    'timestamp': timestamp,
                    'tags': {
                        'service': service_name,
                        'function_name': func_name,
                        'unit': 'seconds'
                    }
                })
                
                metrics.append({
                    'metric_name': 'function.execution.count', 
                    'metric_type': 'counter',
                    'value': stats['call_count'],
                    'timestamp': timestamp,
                    'tags': {
                        'service': service_name,
                        'function_name': func_name
                    }
                })
                
                metrics.append({
                    'metric_name': 'function.error.rate',
                    'metric_type': 'gauge', 
                    'value': error_rate,
                    'timestamp': timestamp,
                    'tags': {
                        'service': service_name,
                        'function_name': func_name,
                        'unit': 'ratio'
                    }
                })
        
        # API call metrics (lightweight)
        for api_name, stats in self._api_calls.items():
            if stats['call_count'] > 0:
                avg_duration = stats['total_time'] / stats['call_count'] 
                success_rate = stats['success_count'] / stats['call_count']
                
                metrics.append({
                    'metric_name': 'api.call.duration',
                    'metric_type': 'gauge',
                    'value': avg_duration,
                    'timestamp': timestamp,
                    'tags': {
                        'service': service_name,
                        'api_name': api_name,
                        'unit': 'seconds'
                    }
                })
                
                metrics.append({
                    'metric_name': 'api.call.count',
                    'metric_type': 'counter',
                    'value': stats['call_count'], 
                    'timestamp': timestamp,
                    'tags': {
                        'service': service_name,
                        'api_name': api_name
                    }
                })
                
                metrics.append({
                    'metric_name': 'api.success.rate',
                    'metric_type': 'gauge',
                    'value': success_rate,
                    'timestamp': timestamp, 
                    'tags': {
                        'service': service_name,
                        'api_name': api_name,
                        'unit': 'ratio'
                    }
                })
        
        return {
            'service_name': service_name,
            'timestamp': timestamp,
            'metrics': metrics,
            'metadata': {
                'total_functions_monitored': len(self._function_stats),
                'total_apis_monitored': len(self._api_calls),
                'monitoring_enabled': not self._monitoring_disabled
            }
        }


# Global performance monitor instance
performance_monitor = PerformanceMonitor()


# Convenience functions for easy access
def monitor_function(func_name: Optional[str] = None):
    """Convenience decorator for monitoring function performance."""
    return performance_monitor.monitor_function(func_name)


def track_api_call(api_name: str, endpoint: Optional[str] = None):
    """Convenience context manager for tracking API calls."""
    return performance_monitor.track_api_call(api_name, endpoint)


def get_performance_report() -> str:
    """Get a comprehensive performance report."""
    return performance_monitor.generate_performance_report()


def get_function_stats(func_name: Optional[str] = None) -> Dict[str, Any]:
    """Get function performance statistics."""
    return performance_monitor.get_function_performance(func_name)


def get_api_stats(api_name: Optional[str] = None) -> Dict[str, Any]:
    """Get API call performance statistics."""
    return performance_monitor.get_api_call_performance(api_name)


def get_slowest_functions(limit: int = 10) -> List[Dict[str, Any]]:
    """Get the slowest performing functions."""
    return performance_monitor.get_slowest_functions(limit)


def get_slowest_apis(limit: int = 10) -> List[Dict[str, Any]]:
    """Get the slowest performing API calls."""
    return performance_monitor.get_slowest_api_calls(limit)


def clear_performance_data():
    """Clear all performance monitoring data."""
    performance_monitor.clear_statistics()


def export_external_apm_metrics(service_name: str = "praisonai-agents") -> Dict[str, Any]:
    """Export lightweight metrics for external APM tools."""
    return performance_monitor.export_metrics_for_external_apm(service_name)