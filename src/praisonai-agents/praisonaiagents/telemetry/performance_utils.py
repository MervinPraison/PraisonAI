"""
Performance Analysis Utilities for PraisonAI

This module provides advanced analysis tools for function flow visualization,
performance bottleneck identification, and comprehensive reporting.

Features:
- Function flow analysis and visualization (opt-in via PRAISONAI_FLOW_ANALYSIS_ENABLED)
- Performance bottleneck detection
- Execution path mapping
- Performance trend analysis
- Advanced reporting utilities
"""

import os
import json
from collections import defaultdict
from typing import Dict, Any, List, Optional
from datetime import datetime
import logging
from dataclasses import dataclass

try:
    from .performance_monitor import performance_monitor
    PERFORMANCE_MONITOR_AVAILABLE = True
except ImportError:
    PERFORMANCE_MONITOR_AVAILABLE = False

logger = logging.getLogger(__name__)

# Check if expensive flow analysis should be enabled (opt-in only)
_FLOW_ANALYSIS_ENABLED = os.environ.get('PRAISONAI_FLOW_ANALYSIS_ENABLED', '').lower() in ('true', '1', 'yes')

# Performance analysis thresholds
BOTTLENECK_THRESHOLD_AVERAGE = 1.0  # seconds - average duration to consider bottleneck
BOTTLENECK_THRESHOLD_MAX = 5.0      # seconds - max duration to consider bottleneck
HIGH_SEVERITY_THRESHOLD = 2.0       # seconds - average duration for high severity bottleneck




class FunctionFlowAnalyzer:
    """
    Advanced function flow analysis and visualization.
    
    Provides tools for analyzing function execution patterns,
    identifying bottlenecks, and visualizing execution flow.
    """
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        
        # Check if performance monitoring is disabled
        from .telemetry import _is_monitoring_disabled
        self._analysis_disabled = _is_monitoring_disabled()
    
    def analyze_execution_flow(self, flow_data: Optional[List[Dict]] = None) -> Dict[str, Any]:
        """
        Analyze function execution flow to identify patterns and bottlenecks.
        
        Note: Expensive flow analysis operations are opt-in only via PRAISONAI_FLOW_ANALYSIS_ENABLED
        environment variable to avoid performance overhead.
        
        Args:
            flow_data: Optional flow data, or None to use current monitor data
            
        Returns:
            Analysis results with flow patterns, bottlenecks, and statistics
        """
        # Early exit if analysis is disabled
        if self._analysis_disabled:
            return {"message": "Flow analysis disabled via environment variables"}
        
        if flow_data is None:
            if not PERFORMANCE_MONITOR_AVAILABLE:
                return {"error": "Performance monitor not available and no flow data provided"}
            flow_data = performance_monitor.get_function_flow()
        
        if not flow_data:
            return {"message": "No flow data available"}
        
        analysis = {
            "total_events": len(flow_data),
            "statistics": self._calculate_flow_statistics(flow_data)
        }
        
        # Only include expensive analysis if explicitly enabled
        if _FLOW_ANALYSIS_ENABLED:
            analysis.update({
                "execution_patterns": self._analyze_patterns(flow_data),
                "bottlenecks": self._identify_bottlenecks(flow_data),
                "parallelism": self._analyze_parallelism(flow_data),
                "call_chains": self._build_call_chains(flow_data),
            })
        else:
            analysis["note"] = "Advanced flow analysis disabled. Set PRAISONAI_FLOW_ANALYSIS_ENABLED=true to enable expensive pattern detection."
        
        return analysis
    
    def _analyze_patterns(self, flow_data: List[Dict]) -> Dict[str, Any]:
        """Analyze execution patterns in the flow data (optimized to avoid O(n²) complexity)."""
        patterns = {
            "most_frequent_sequences": [],
            "recursive_calls": [],
            "long_running_chains": [],
            "error_patterns": []
        }
        
        # Limit analysis to reasonable data size to prevent performance issues
        MAX_EVENTS_TO_ANALYZE = 1000
        if len(flow_data) > MAX_EVENTS_TO_ANALYZE:
            # Sample the most recent events instead of analyzing all (create copy to avoid modifying input)
            flow_data = flow_data[-MAX_EVENTS_TO_ANALYZE:].copy()
        
        # Group events by function to find sequences
        function_sequences = defaultdict(list)
        
        for event in flow_data:
            func_name = event.get('function', 'unknown')
            function_sequences[func_name].append(event)
        
        # Find most frequent function sequences (optimized - single pass)
        sequence_counts = defaultdict(int)
        for i in range(len(flow_data) - 1):
            current_func = flow_data[i].get('function')
            next_func = flow_data[i + 1].get('function')
            if current_func and next_func:
                sequence_counts[(current_func, next_func)] += 1
        
        # Sort by frequency
        frequent_sequences = sorted(sequence_counts.items(), key=lambda x: x[1], reverse=True)[:5]
        patterns["most_frequent_sequences"] = [
            {"sequence": f"{seq[0]} -> {seq[1]}", "count": count}
            for seq, count in frequent_sequences
        ]
        
        # Find recursive calls
        for func_name, events in function_sequences.items():
            nested_level = 0
            for event in events:
                if event.get('event') == 'start':
                    nested_level += 1
                    if nested_level > 1:
                        patterns["recursive_calls"].append({
                            "function": func_name,
                            "max_depth": nested_level,
                            "timestamp": event.get('timestamp')
                        })
                elif event.get('event') == 'end':
                    nested_level = max(0, nested_level - 1)
        
        return patterns
    
    def _identify_bottlenecks(self, flow_data: List[Dict]) -> List[Dict[str, Any]]:
        """Identify performance bottlenecks in the execution flow."""
        bottlenecks = []
        
        # Group start/end events
        function_durations = defaultdict(list)
        active_calls = {}
        
        for event in flow_data:
            func_name = event.get('function', 'unknown')
            event_type = event.get('event')
            timestamp = event.get('timestamp')
            thread_id = event.get('thread_id', 0)
            
            if event_type == 'start':
                call_key = f"{func_name}_{thread_id}_{timestamp}"
                active_calls[call_key] = event
            elif event_type == 'end':
                duration = event.get('duration', 0)
                if duration > 0:
                    function_durations[func_name].append(duration)
        
        # Find functions with consistently slow performance
        for func_name, durations in function_durations.items():
            if durations:
                avg_duration = sum(durations) / len(durations)
                max_duration = max(durations)
                
                # Consider it a bottleneck based on defined thresholds
                if avg_duration > BOTTLENECK_THRESHOLD_AVERAGE or max_duration > BOTTLENECK_THRESHOLD_MAX:
                    bottlenecks.append({
                        "function": func_name,
                        "average_duration": avg_duration,
                        "max_duration": max_duration,
                        "call_count": len(durations),
                        "severity": "high" if avg_duration > HIGH_SEVERITY_THRESHOLD else "medium"
                    })
        
        # Sort by severity and duration
        bottlenecks.sort(key=lambda x: x["average_duration"], reverse=True)
        return bottlenecks
    
    def _analyze_parallelism(self, flow_data: List[Dict]) -> Dict[str, Any]:
        """Analyze parallelism and concurrent execution patterns."""
        thread_activities = defaultdict(list)
        
        for event in flow_data:
            thread_id = event.get('thread_id', 0)
            thread_activities[thread_id].append(event)
        
        # Find peak concurrency
        timestamp_activities = defaultdict(int)
        for event in flow_data:
            if event.get('event') == 'start':
                timestamp = event.get('timestamp')
                timestamp_activities[timestamp] += 1
        
        peak_concurrency = max(timestamp_activities.values()) if timestamp_activities else 0
        
        return {
            "total_threads": len(thread_activities),
            "peak_concurrency": peak_concurrency,
            "thread_utilization": {
                str(thread_id): len(events) 
                for thread_id, events in thread_activities.items()
            }
        }
    
    def _build_call_chains(self, flow_data: List[Dict]) -> List[Dict[str, Any]]:
        """Build call chains from flow data."""
        # Track call chains per thread more efficiently
        thread_chains = defaultdict(list)
        call_stacks = defaultdict(list)
        current_chains = defaultdict(list)
        
        for event in flow_data:
            thread_id = event.get('thread_id', 0)
            func_name = event.get('function', 'unknown')
            event_type = event.get('event')
            
            if event_type == 'start':
                call_stacks[thread_id].append(func_name)
                current_chains[thread_id].append(func_name)
            elif event_type == 'end' and call_stacks[thread_id] and call_stacks[thread_id][-1] == func_name:
                call_stacks[thread_id].pop()
                
                # If this completes a top-level call (stack becomes empty), record the chain
                if not call_stacks[thread_id] and current_chains[thread_id]:
                    chain = current_chains[thread_id].copy()
                    thread_chains[thread_id].append({
                        "thread_id": thread_id,
                        "chain_length": len(chain),
                        "functions": chain
                    })
                    current_chains[thread_id].clear()
        
        # Flatten all chains and return top 10
        all_chains = []
        for chains in thread_chains.values():
            all_chains.extend(chains)
        
        return all_chains[:10]
    
    def _calculate_flow_statistics(self, flow_data: List[Dict]) -> Dict[str, Any]:
        """Calculate comprehensive flow statistics."""
        total_events = len(flow_data)
        start_events = [e for e in flow_data if e.get('event') == 'start']
        end_events = [e for e in flow_data if e.get('event') == 'end']
        successful_events = [e for e in end_events if e.get('success', True)]
        
        total_duration = sum(e.get('duration', 0) for e in end_events)
        
        return {
            "total_events": total_events,
            "function_calls": len(start_events),
            "completed_calls": len(end_events),
            "successful_calls": len(successful_events),
            "success_rate": len(successful_events) / len(end_events) if end_events else 0,
            "total_execution_time": total_duration,
            "average_execution_time": total_duration / len(end_events) if end_events else 0
        }
    
    def visualize_flow(self, flow_data: Optional[List[Dict]] = None, 
                      format: str = "text") -> str:
        """
        Create a visual representation of the function execution flow.
        
        Args:
            flow_data: Optional flow data, or None to use current monitor data
            format: Output format ("text", "mermaid", "json")
            
        Returns:
            Formatted visualization string
        """
        if flow_data is None:
            if not PERFORMANCE_MONITOR_AVAILABLE:
                return "Performance monitor not available and no flow data provided"
            flow_data = performance_monitor.get_function_flow(50)  # Last 50 events
        
        if not flow_data:
            return "No flow data available"
        
        if format == "text":
            return self._create_text_visualization(flow_data)
        elif format == "mermaid":
            return self._create_mermaid_diagram(flow_data)
        elif format == "json":
            return json.dumps(flow_data, indent=2)
        else:
            return "Unknown format"
    
    def _create_text_visualization(self, flow_data: List[Dict]) -> str:
        """Create a text-based visualization of the execution flow."""
        lines = []
        lines.append("📊 FUNCTION EXECUTION FLOW VISUALIZATION")
        lines.append("=" * 60)
        
        # Group by thread for better visualization
        threads = defaultdict(list)
        for event in flow_data:
            thread_id = event.get('thread_id', 0)
            threads[thread_id].append(event)
        
        for thread_id, events in threads.items():
            lines.append(f"\n🧵 Thread {thread_id}:")
            lines.append("-" * 30)
            
            call_stack = []
            for event in events:
                func_name = event.get('function', 'unknown')
                event_type = event.get('event')
                duration = event.get('duration', 0)
                success = event.get('success', True)
                
                if event_type == 'start':
                    call_stack.append(func_name)
                    indent = "  " * (len(call_stack) - 1)
                    lines.append(f"{indent}🟢 START {func_name}")
                elif event_type == 'end':
                    if call_stack and call_stack[-1] == func_name:
                        call_stack.pop()
                    indent = "  " * len(call_stack)
                    status = "✅" if success else "❌"
                    lines.append(f"{indent}{status} END   {func_name} ({duration:.3f}s)")
        
        return "\n".join(lines)
    
    def _create_mermaid_diagram(self, flow_data: List[Dict]) -> str:
        """Create a Mermaid diagram representation of the flow."""
        lines = ["graph TD"]
        
        # Build flow connections
        node_counter = 0
        node_map = {}
        
        for event in flow_data:
            if event.get('event') == 'start':
                func_name = event.get('function', 'unknown')
                if func_name not in node_map:
                    node_map[func_name] = f"n{node_counter}"
                    node_counter += 1
        
        # Add nodes
        for func_name, node_id in node_map.items():
            lines.append(f"    {node_id}[{func_name}]")
        
        # Add connections based on call sequence
        prev_func = None
        for event in flow_data:
            if event.get('event') == 'start':
                curr_func = event.get('function', 'unknown')
                if prev_func and curr_func != prev_func:
                    prev_node = node_map.get(prev_func)
                    curr_node = node_map.get(curr_func)
                    if prev_node and curr_node:
                        lines.append(f"    {prev_node} --> {curr_node}")
                prev_func = curr_func
        
        return "\n".join(lines)


class PerformanceAnalyzer:
    """
    Comprehensive performance analysis tools.
    
    Provides advanced analysis capabilities for identifying performance
    issues, trends, and optimization opportunities.
    """
    
    def __init__(self):
        self.flow_analyzer = FunctionFlowAnalyzer()
    
    def analyze_performance_trends(self, hours_back: int = 24) -> Dict[str, Any]:
        """
        Analyze performance trends over time.
        
        Args:
            hours_back: Number of hours to analyze
            
        Returns:
            Trend analysis results
        """
        if not PERFORMANCE_MONITOR_AVAILABLE:
            return {"error": "Performance monitor not available"}
        
        # Get current performance data
        func_stats = performance_monitor.get_function_performance()
        api_stats = performance_monitor.get_api_call_performance()
        
        trends = {
            "analysis_period_hours": hours_back,
            "function_trends": self._analyze_function_trends(func_stats),
            "api_trends": self._analyze_api_trends(api_stats),
            "recommendations": self._generate_recommendations(func_stats, api_stats)
        }
        
        return trends
    
    def _analyze_function_trends(self, func_stats: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze function performance trends."""
        trends = {
            "improving": [],
            "degrading": [],
            "stable": []
        }
        
        for func_name, stats in func_stats.items():
            recent_times = stats.get('recent_times', [])
            if len(recent_times) >= 10:  # Need sufficient data
                # Compare first half to second half
                mid_point = len(recent_times) // 2
                first_half_avg = sum(recent_times[:mid_point]) / mid_point
                second_half_avg = sum(recent_times[mid_point:]) / (len(recent_times) - mid_point)
                
                if first_half_avg != 0:
                    change_percent = ((second_half_avg - first_half_avg) / first_half_avg) * 100
                else:
                    change_percent = 0.0  # No change if first half average is zero
                
                trend_data = {
                    "function": func_name,
                    "change_percent": change_percent,
                    "first_half_avg": first_half_avg,
                    "second_half_avg": second_half_avg
                }
                
                if change_percent < -5:  # Improving (getting faster)
                    trends["improving"].append(trend_data)
                elif change_percent > 5:  # Degrading (getting slower)
                    trends["degrading"].append(trend_data)
                else:
                    trends["stable"].append(trend_data)
        
        return trends
    
    def _analyze_api_trends(self, api_stats: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze API performance trends."""
        trends = {
            "fastest_apis": [],
            "slowest_apis": [],
            "most_reliable": [],
            "least_reliable": []
        }
        
        api_performance = []
        for api_name, stats in api_stats.items():
            if stats.get('call_count', 0) > 0:
                avg_time = stats['total_time'] / stats['call_count']
                success_rate = stats.get('success_rate', 0)
                
                api_performance.append({
                    "api": api_name,
                    "average_time": avg_time,
                    "success_rate": success_rate,
                    "call_count": stats['call_count']
                })
        
        # Sort by performance metrics
        fastest = sorted(api_performance, key=lambda x: x['average_time'])[:5]
        slowest = sorted(api_performance, key=lambda x: x['average_time'], reverse=True)[:5]
        most_reliable = sorted(api_performance, key=lambda x: x['success_rate'], reverse=True)[:5]
        least_reliable = sorted(api_performance, key=lambda x: x['success_rate'])[:5]
        
        trends["fastest_apis"] = fastest
        trends["slowest_apis"] = slowest
        trends["most_reliable"] = most_reliable
        trends["least_reliable"] = least_reliable
        
        return trends
    
    def _generate_recommendations(self, func_stats: Dict[str, Any], 
                                api_stats: Dict[str, Any]) -> List[str]:
        """Generate performance optimization recommendations."""
        recommendations = []
        
        # Function recommendations
        for func_name, stats in func_stats.items():
            if stats.get('call_count', 0) > 0:
                avg_time = stats['total_time'] / stats['call_count']
                error_rate = stats['error_count'] / stats['call_count']
                
                if avg_time > 2.0:
                    recommendations.append(
                        f"⚠️ Function '{func_name}' has high average execution time ({avg_time:.2f}s). Consider optimization."
                    )
                
                if error_rate > 0.1:
                    recommendations.append(
                        f"🚨 Function '{func_name}' has high error rate ({error_rate*100:.1f}%). Investigate error handling."
                    )
        
        # API recommendations
        for api_name, stats in api_stats.items():
            if stats.get('call_count', 0) > 0:
                avg_time = stats['total_time'] / stats['call_count']
                success_rate = stats.get('success_rate', 1.0)
                
                if avg_time > 5.0:
                    recommendations.append(
                        f"🐌 API '{api_name}' has high average response time ({avg_time:.2f}s). Consider caching or optimization."
                    )
                
                if success_rate < 0.9:
                    recommendations.append(
                        f"⚠️ API '{api_name}' has low success rate ({success_rate*100:.1f}%). Check error handling and retry logic."
                    )
        
        if not recommendations:
            recommendations.append("✅ No major performance issues detected. System is performing well!")
        
        return recommendations
    
    def generate_comprehensive_report(self) -> str:
        """Generate a comprehensive performance analysis report."""
        if not PERFORMANCE_MONITOR_AVAILABLE:
            return "Performance monitor not available"
        
        report_lines = []
        report_lines.append("=" * 80)
        report_lines.append("COMPREHENSIVE PERFORMANCE ANALYSIS REPORT")
        report_lines.append("=" * 80)
        report_lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report_lines.append("")
        
        # Basic performance report
        basic_report = performance_monitor.generate_performance_report()
        report_lines.append(basic_report)
        report_lines.append("")
        
        # Flow analysis
        report_lines.append("🔄 EXECUTION FLOW ANALYSIS")
        report_lines.append("-" * 40)
        flow_analysis = self.flow_analyzer.analyze_execution_flow()
        
        if "bottlenecks" in flow_analysis:
            bottlenecks = flow_analysis["bottlenecks"]
            if bottlenecks:
                report_lines.append("🚨 IDENTIFIED BOTTLENECKS:")
                for bottleneck in bottlenecks[:5]:
                    report_lines.append(f"• {bottleneck['function']}: {bottleneck['average_duration']:.2f}s avg, {bottleneck['severity']} severity")
            else:
                report_lines.append("✅ No significant bottlenecks identified")
        
        report_lines.append("")
        
        # Performance trends
        report_lines.append("📈 PERFORMANCE TRENDS")
        report_lines.append("-" * 40)
        trends = self.analyze_performance_trends()
        
        if "recommendations" in trends:
            recommendations = trends["recommendations"]
            report_lines.append("💡 RECOMMENDATIONS:")
            for rec in recommendations:
                report_lines.append(f"  {rec}")
        
        report_lines.append("")
        report_lines.append("=" * 80)
        
        return "\n".join(report_lines)


# Global instances for easy access
flow_analyzer = FunctionFlowAnalyzer()
performance_analyzer = PerformanceAnalyzer()


# Convenience functions
def analyze_function_flow() -> Dict[str, Any]:
    """Analyze current function execution flow."""
    return flow_analyzer.analyze_execution_flow()


def visualize_execution_flow(format: str = "text") -> str:
    """Visualize function execution flow."""
    return flow_analyzer.visualize_flow(format=format)


def analyze_performance_trends() -> Dict[str, Any]:
    """Analyze performance trends."""
    return performance_analyzer.analyze_performance_trends()


def generate_comprehensive_report() -> str:
    """Generate comprehensive performance analysis report."""
    return performance_analyzer.generate_comprehensive_report()