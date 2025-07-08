"""
Example tools.py file with integrated latency tracking.

This shows how to add latency tracking to your tools without modifying core files.
Place this as tools.py in your project root for automatic loading.
"""

import time
from typing import List, Dict
from latency_tracker_tool import tracker, track_latency

# Example 1: Simple tool with manual tracking
def search_with_tracking(query: str) -> str:
    """
    Search tool with built-in latency tracking.
    
    Args:
        query: Search query string
    
    Returns:
        str: Search results
    """
    # Manual tracking approach
    tracker.start_timer("tool_search", "current_request")
    
    # Simulate search operation
    time.sleep(0.1)  # Simulate API call
    result = f"Found 3 results for '{query}'"
    
    elapsed = tracker.end_timer("tool_search", "current_request")
    
    # Include timing in result (optional)
    return f"{result} (took {elapsed:.3f}s)"


# Example 2: Tool with decorator-based tracking
@track_latency("tool_calculation", "current_request")
def calculate_with_tracking(expression: str) -> str:
    """
    Calculator tool with automatic latency tracking via decorator.
    
    Args:
        expression: Mathematical expression to evaluate
    
    Returns:
        str: Calculation result
    """
    # Simulate calculation
    time.sleep(0.05)
    
    try:
        result = eval(expression)
        return f"Result: {result}"
    except Exception as e:
        return f"Error: {str(e)}"


# Example 3: Tool with context manager tracking
def analyze_with_tracking(data: str) -> Dict[str, any]:
    """
    Analysis tool with fine-grained latency tracking.
    
    Args:
        data: Data to analyze
    
    Returns:
        dict: Analysis results with timing breakdown
    """
    results = {}
    
    # Track different phases of analysis
    with tracker.track("analysis_preprocessing", "current_request"):
        # Simulate preprocessing
        time.sleep(0.02)
        processed_data = data.lower().strip()
    
    with tracker.track("analysis_main", "current_request"):
        # Simulate main analysis
        time.sleep(0.08)
        word_count = len(processed_data.split())
        char_count = len(processed_data)
    
    with tracker.track("analysis_postprocessing", "current_request"):
        # Simulate postprocessing
        time.sleep(0.01)
        results = {
            "word_count": word_count,
            "char_count": char_count,
            "processed": True
        }
    
    # Get metrics for this analysis
    metrics = tracker.get_metrics("current_request")
    if "analysis_preprocessing" in metrics:
        results["timing"] = {
            "preprocessing": metrics["analysis_preprocessing"]["latest"],
            "main": metrics["analysis_main"]["latest"],
            "postprocessing": metrics["analysis_postprocessing"]["latest"]
        }
    
    return results


# Latency reporting tool - allows agents to get latency metrics
def get_latency_report(request_id: str = "current_request") -> str:
    """
    Get a latency report for the current or specified request.
    
    Args:
        request_id: Request identifier (default: "current_request")
    
    Returns:
        str: Formatted latency report
    """
    metrics = tracker.get_metrics(request_id)
    
    if not metrics:
        return "No latency data available for this request."
    
    report = f"Latency Report for {request_id}:\n"
    report += "-" * 40 + "\n"
    
    total_time = 0
    for phase, data in metrics.items():
        phase_time = data['total']
        total_time += phase_time
        report += f"{phase}: {phase_time:.3f}s (avg: {data['average']:.3f}s, count: {data['count']})\n"
    
    report += "-" * 40 + "\n"
    report += f"Total tracked time: {total_time:.3f}s\n"
    
    return report


# Clear latency data tool
def clear_latency_data(request_id: str = None) -> str:
    """
    Clear latency tracking data.
    
    Args:
        request_id: Specific request to clear (None clears all)
    
    Returns:
        str: Confirmation message
    """
    tracker.clear(request_id)
    if request_id:
        return f"Cleared latency data for request: {request_id}"
    else:
        return "Cleared all latency tracking data"