"""
Enhanced Performance Monitor for PraisonAI

This module provides comprehensive performance tracking without requiring code changes.
It uses monkey patching, decorators, and context managers to instrument existing code
and provide detailed performance insights.
"""

import time
import json
import threading
import functools
import inspect
import sys
import traceback
from typing import Dict, Any, List, Optional, Callable, Tuple
from collections import defaultdict, deque
from contextlib import contextmanager
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
from pathlib import Path
import logging


@dataclass
class FunctionCall:
    """Represents a tracked function call."""
    function_name: str
    module_name: str
    start_time: float
    end_time: Optional[float] = None
    duration: Optional[float] = None
    args_count: int = 0
    kwargs_count: int = 0
    success: bool = True
    error: Optional[str] = None
    call_depth: int = 0
    parent_call: Optional[str] = None
    children: List[str] = None
    
    def __post_init__(self):
        if self.children is None:
            self.children = []


@dataclass 
class APICall:
    """Represents a tracked API call."""
    api_type: str  # 'llm', 'http', 'tool'
    endpoint: str
    method: str
    start_time: float
    end_time: Optional[float] = None
    duration: Optional[float] = None
    status_code: Optional[int] = None
    request_size: Optional[int] = None
    response_size: Optional[int] = None
    success: bool = True
    error: Optional[str] = None
    provider: Optional[str] = None
    model: Optional[str] = None


class PerformanceMonitor:
    """
    Enhanced performance monitoring system for PraisonAI.
    
    Provides non-invasive performance tracking of:
    - Function calls and execution flow
    - API calls (LLM, HTTP, tools)
    - Memory and resource usage
    - Performance bottlenecks and analysis
    """
    
    def __init__(self, enabled: bool = True):
        self.enabled = enabled
        self.logger = logging.getLogger(__name__)
        
        # Thread-safe storage
        self._lock = threading.RLock()
        self._function_calls: Dict[str, FunctionCall] = {}
        self._api_calls: List[APICall] = []
        self._call_stack: List[str] = []
        self._session_start = time.time()
        
        # Performance statistics
        self._stats = {
            'total_functions_called': 0,
            'total_api_calls': 0,
            'total_execution_time': 0.0,
            'slowest_functions': [],
            'most_called_functions': defaultdict(int),
            'api_call_summary': defaultdict(lambda: {'count': 0, 'total_time': 0.0})
        }
        
        # Configuration
        self.max_stored_calls = 10000  # Prevent memory leaks
        self.track_call_hierarchy = True
        self.track_arguments = False  # Privacy: don't track args by default
        
    def enable(self):
        """Enable performance monitoring."""
        self.enabled = True
        self.logger.info("Performance monitoring enabled")
        
    def disable(self):
        """Disable performance monitoring."""
        self.enabled = False
        self.logger.info("Performance monitoring disabled")
        
    def is_enabled(self) -> bool:
        """Check if monitoring is enabled."""
        return self.enabled
        
    @contextmanager
    def track_function(self, func_name: str, module_name: str = "unknown"):
        """Context manager to track function execution."""
        if not self.enabled:
            yield
            return
            
        call_id = f"{module_name}.{func_name}_{int(time.time() * 1000000)}"
        start_time = time.time()
        
        # Create function call record
        with self._lock:
            parent_call = self._call_stack[-1] if self._call_stack else None
            call_depth = len(self._call_stack)
            
            func_call = FunctionCall(
                function_name=func_name,
                module_name=module_name,
                start_time=start_time,
                call_depth=call_depth,
                parent_call=parent_call
            )
            
            self._function_calls[call_id] = func_call
            self._call_stack.append(call_id)
            
            # Update parent's children
            if parent_call and parent_call in self._function_calls:
                self._function_calls[parent_call].children.append(call_id)
        
        try:
            yield call_id
            
        except Exception as e:
            # Track errors
            with self._lock:
                self._function_calls[call_id].success = False
                self._function_calls[call_id].error = str(e)
            raise
            
        finally:
            # Complete the tracking
            end_time = time.time()
            duration = end_time - start_time
            
            with self._lock:
                self._function_calls[call_id].end_time = end_time
                self._function_calls[call_id].duration = duration
                
                if self._call_stack and self._call_stack[-1] == call_id:
                    self._call_stack.pop()
                    
                # Update statistics
                self._stats['total_functions_called'] += 1
                self._stats['total_execution_time'] += duration
                self._stats['most_called_functions'][func_name] += 1
                
                # Cleanup old calls to prevent memory leaks
                if len(self._function_calls) > self.max_stored_calls:
                    self._cleanup_old_calls()
    
    def track_api_call(self, api_type: str, endpoint: str, method: str = "POST", 
                       provider: str = None, model: str = None) -> str:
        """Start tracking an API call."""
        if not self.enabled:
            return ""
            
        api_call = APICall(
            api_type=api_type,
            endpoint=endpoint, 
            method=method,
            start_time=time.time(),
            provider=provider,
            model=model
        )
        
        with self._lock:
            self._api_calls.append(api_call)
            call_id = str(len(self._api_calls) - 1)
            
        return call_id
    
    def complete_api_call(self, call_id: str, success: bool = True, 
                         status_code: int = None, error: str = None,
                         request_size: int = None, response_size: int = None):
        """Complete tracking of an API call."""
        if not self.enabled or not call_id.isdigit():
            return
            
        call_idx = int(call_id)
        
        with self._lock:
            if call_idx < len(self._api_calls):
                api_call = self._api_calls[call_idx]
                api_call.end_time = time.time()
                api_call.duration = api_call.end_time - api_call.start_time
                api_call.success = success
                api_call.status_code = status_code
                api_call.error = error
                api_call.request_size = request_size
                api_call.response_size = response_size
                
                # Update statistics
                self._stats['total_api_calls'] += 1
                key = f"{api_call.api_type}_{api_call.provider or 'unknown'}"
                self._stats['api_call_summary'][key]['count'] += 1
                self._stats['api_call_summary'][key]['total_time'] += api_call.duration
    
    def get_function_metrics(self, function_name: str = None) -> Dict[str, Any]:
        """Get performance metrics for functions."""
        with self._lock:
            if function_name:
                # Get metrics for specific function
                matching_calls = [
                    call for call in self._function_calls.values()
                    if call.function_name == function_name and call.duration is not None
                ]
                
                if not matching_calls:
                    return {}
                    
                durations = [call.duration for call in matching_calls]
                return {
                    'function_name': function_name,
                    'total_calls': len(matching_calls),
                    'total_time': sum(durations),
                    'average_time': sum(durations) / len(durations),
                    'min_time': min(durations),
                    'max_time': max(durations),
                    'success_rate': sum(1 for call in matching_calls if call.success) / len(matching_calls)
                }
            else:
                # Get summary for all functions
                function_stats = defaultdict(lambda: {
                    'calls': [], 'total_time': 0, 'call_count': 0
                })
                
                for call in self._function_calls.values():
                    if call.duration is not None:
                        function_stats[call.function_name]['calls'].append(call.duration)
                        function_stats[call.function_name]['total_time'] += call.duration
                        function_stats[call.function_name]['call_count'] += 1
                
                result = {}
                for func_name, stats in function_stats.items():
                    durations = stats['calls']
                    if durations:
                        result[func_name] = {
                            'total_calls': len(durations),
                            'total_time': stats['total_time'],
                            'average_time': stats['total_time'] / len(durations),
                            'min_time': min(durations),
                            'max_time': max(durations)
                        }
                        
                return result
    
    def get_api_metrics(self, api_type: str = None) -> Dict[str, Any]:
        """Get performance metrics for API calls."""
        with self._lock:
            if api_type:
                matching_calls = [
                    call for call in self._api_calls
                    if call.api_type == api_type and call.duration is not None
                ]
            else:
                matching_calls = [
                    call for call in self._api_calls
                    if call.duration is not None
                ]
            
            if not matching_calls:
                return {}
            
            durations = [call.duration for call in matching_calls]
            successful_calls = [call for call in matching_calls if call.success]
            
            # Group by provider/endpoint for detailed analysis
            by_provider = defaultdict(list)
            for call in matching_calls:
                key = f"{call.provider or 'unknown'}_{call.endpoint}"
                by_provider[key].append(call.duration)
            
            provider_stats = {}
            for provider, times in by_provider.items():
                provider_stats[provider] = {
                    'count': len(times),
                    'total_time': sum(times),
                    'average_time': sum(times) / len(times),
                    'min_time': min(times),
                    'max_time': max(times)
                }
            
            return {
                'total_calls': len(matching_calls),
                'successful_calls': len(successful_calls),
                'success_rate': len(successful_calls) / len(matching_calls),
                'total_time': sum(durations),
                'average_time': sum(durations) / len(durations),
                'min_time': min(durations),
                'max_time': max(durations),
                'by_provider': provider_stats
            }
    
    def get_call_hierarchy(self, max_depth: int = 5) -> Dict[str, Any]:
        """Get function call hierarchy and flow analysis."""
        if not self.track_call_hierarchy:
            return {}
            
        with self._lock:
            # Find root calls (no parent)
            root_calls = [
                call for call in self._function_calls.values()
                if call.parent_call is None and call.duration is not None
            ]
            
            def build_hierarchy(call: FunctionCall, depth: int = 0) -> Dict[str, Any]:
                if depth > max_depth:
                    return {}
                    
                children_data = []
                for child_id in call.children:
                    if child_id in self._function_calls:
                        child_call = self._function_calls[child_id]
                        child_data = build_hierarchy(child_call, depth + 1)
                        if child_data:
                            children_data.append(child_data)
                
                return {
                    'function': call.function_name,
                    'module': call.module_name,
                    'duration': call.duration,
                    'start_time': call.start_time,
                    'success': call.success,
                    'depth': depth,
                    'children': children_data
                }
            
            hierarchy = []
            for root_call in root_calls[:10]:  # Limit to prevent huge output
                hierarchy.append(build_hierarchy(root_call))
                
            return {'call_hierarchy': hierarchy}
    
    def get_performance_summary(self) -> Dict[str, Any]:
        """Get comprehensive performance summary."""
        with self._lock:
            session_duration = time.time() - self._session_start
            
            # Find slowest functions
            slowest_functions = []
            function_times = defaultdict(list)
            
            for call in self._function_calls.values():
                if call.duration is not None:
                    function_times[call.function_name].append(call.duration)
            
            for func_name, times in function_times.items():
                avg_time = sum(times) / len(times)
                slowest_functions.append({
                    'function': func_name,
                    'average_time': avg_time,
                    'max_time': max(times),
                    'call_count': len(times)
                })
            
            slowest_functions.sort(key=lambda x: x['average_time'], reverse=True)
            
            # API call summary by type
            api_summary = defaultdict(lambda: {'count': 0, 'total_time': 0.0, 'errors': 0})
            for call in self._api_calls:
                if call.duration is not None:
                    key = call.api_type
                    api_summary[key]['count'] += 1
                    api_summary[key]['total_time'] += call.duration
                    if not call.success:
                        api_summary[key]['errors'] += 1
            
            # Convert defaultdict to regular dict for JSON serialization
            api_summary_dict = {}
            for key, value in api_summary.items():
                api_summary_dict[key] = {
                    'count': value['count'],
                    'total_time': value['total_time'],
                    'average_time': value['total_time'] / value['count'] if value['count'] > 0 else 0,
                    'errors': value['errors'],
                    'success_rate': (value['count'] - value['errors']) / value['count'] if value['count'] > 0 else 0
                }
            
            return {
                'session_duration': session_duration,
                'total_function_calls': len([c for c in self._function_calls.values() if c.duration is not None]),
                'total_api_calls': len([c for c in self._api_calls if c.duration is not None]),
                'total_execution_time': sum(c.duration for c in self._function_calls.values() if c.duration is not None),
                'slowest_functions': slowest_functions[:10],
                'api_call_summary': api_summary_dict,
                'memory_usage': self._get_memory_usage(),
                'errors': len([c for c in self._function_calls.values() if not c.success])
            }
    
    def export_metrics(self, format: str = 'json', filepath: str = None) -> str:
        """Export performance metrics to file or return as string."""
        data = {
            'summary': self.get_performance_summary(),
            'function_metrics': self.get_function_metrics(),
            'api_metrics': self.get_api_metrics(),
            'call_hierarchy': self.get_call_hierarchy(),
            'export_timestamp': datetime.now().isoformat()
        }
        
        if format.lower() == 'json':
            json_str = json.dumps(data, indent=2, default=str)
            if filepath:
                with open(filepath, 'w') as f:
                    f.write(json_str)
            return json_str
        else:
            raise ValueError(f"Unsupported export format: {format}")
    
    def clear_metrics(self):
        """Clear all stored performance metrics."""
        with self._lock:
            self._function_calls.clear()
            self._api_calls.clear()
            self._call_stack.clear()
            self._stats = {
                'total_functions_called': 0,
                'total_api_calls': 0,
                'total_execution_time': 0.0,
                'slowest_functions': [],
                'most_called_functions': defaultdict(int),
                'api_call_summary': defaultdict(lambda: {'count': 0, 'total_time': 0.0})
            }
            self._session_start = time.time()
            
        self.logger.info("Performance metrics cleared")
    
    def _cleanup_old_calls(self):
        """Remove oldest function calls to prevent memory leaks."""
        # Keep only the most recent calls
        keep_count = int(self.max_stored_calls * 0.8)  # Keep 80%
        
        # Sort by start time and keep the most recent
        sorted_calls = sorted(
            self._function_calls.items(),
            key=lambda x: x[1].start_time,
            reverse=True
        )
        
        # Keep the most recent calls
        self._function_calls = dict(sorted_calls[:keep_count])
        
    def _get_memory_usage(self) -> Dict[str, int]:
        """Get current memory usage statistics."""
        try:
            import psutil
            process = psutil.Process()
            return {
                'rss_mb': int(process.memory_info().rss / 1024 / 1024),
                'vms_mb': int(process.memory_info().vms / 1024 / 1024),
                'percent': round(process.memory_percent(), 2)
            }
        except ImportError:
            # psutil not available
            return {'rss_mb': 0, 'vms_mb': 0, 'percent': 0.0}


# Global performance monitor instance
_performance_monitor = None


def get_performance_monitor() -> PerformanceMonitor:
    """Get the global performance monitor instance."""
    global _performance_monitor
    if _performance_monitor is None:
        _performance_monitor = PerformanceMonitor()
    return _performance_monitor


def enable_performance_monitoring():
    """Enable global performance monitoring."""
    monitor = get_performance_monitor()
    monitor.enable()


def disable_performance_monitoring():
    """Disable global performance monitoring."""
    monitor = get_performance_monitor()
    monitor.disable()


def track_function_performance(func_name: str = None):
    """Decorator to track function performance."""
    def decorator(func: Callable) -> Callable:
        name = func_name or func.__name__
        module = getattr(func, '__module__', 'unknown')
        
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            monitor = get_performance_monitor()
            with monitor.track_function(name, module):
                return func(*args, **kwargs)
        return wrapper
    return decorator


@contextmanager
def track_api_performance(api_type: str, endpoint: str, method: str = "POST",
                         provider: str = None, model: str = None):
    """Context manager to track API call performance."""
    monitor = get_performance_monitor()
    call_id = monitor.track_api_call(api_type, endpoint, method, provider, model)
    
    try:
        yield
        monitor.complete_api_call(call_id, success=True)
    except Exception as e:
        monitor.complete_api_call(call_id, success=False, error=str(e))
        raise