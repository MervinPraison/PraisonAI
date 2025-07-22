# Enhanced Performance Monitoring for PraisonAI

This guide covers the comprehensive performance monitoring system built into PraisonAI that allows you to track function performance, API calls, and execution flow **without making any changes to your existing code**.

## Table of Contents

1. [Quick Start](#quick-start)
2. [Features](#features)
3. [No-Code Setup](#no-code-setup)
4. [Performance Analysis](#performance-analysis)
5. [Web Dashboard](#web-dashboard)
6. [CLI Tools](#cli-tools)
7. [API Reference](#api-reference)
8. [Examples](#examples)
9. [Troubleshooting](#troubleshooting)

## Quick Start

### Enable Monitoring (Zero Code Changes Required)

```python
from praisonaiagents import (
    enable_performance_monitoring,
    enable_auto_instrumentation,
    start_performance_dashboard
)

# Enable performance tracking
enable_performance_monitoring()
enable_auto_instrumentation()  # Automatically track all PraisonAI functions

# Start web dashboard (optional)
dashboard_url = start_performance_dashboard(port=8888)
print(f"Dashboard available at: {dashboard_url}")

# Use PraisonAI normally - no code changes needed!
from praisonaiagents import Agent

agent = Agent(name="MyAgent", role="Assistant")
response = agent.chat("Hello, world!")

# Get performance insights
from praisonaiagents import get_performance_monitor
monitor = get_performance_monitor()
summary = monitor.get_performance_summary()
print(f"Total function calls: {summary['total_function_calls']}")
print(f"API calls: {summary['total_api_calls']}")
```

### Using CLI Tools

```bash
# Enable monitoring
praisonai-perf enable --auto-instrument

# Check status
praisonai-perf status

# View performance summary
praisonai-perf summary

# Analyze functions
praisonai-perf functions --top 10

# Start dashboard
praisonai-perf dashboard --port 8888

# Export metrics
praisonai-perf export --output metrics.json
```

## Features

### ✅ What Gets Tracked Automatically

- **Function Calls**: All PraisonAI agent methods, task execution, tool calls
- **API Calls**: LLM APIs (OpenAI, Anthropic, Google, etc.), HTTP requests
- **Execution Flow**: Call hierarchy and function dependencies
- **Timing**: Precise execution times for all operations
- **Memory Usage**: Real-time memory consumption tracking
- **Error Rates**: Success/failure rates for all operations
- **Performance Bottlenecks**: Automatically identified slow functions

### 🚀 Key Benefits

1. **Zero Code Changes**: Works with existing PraisonAI applications
2. **Non-Invasive**: Uses monkey patching for transparent tracking
3. **Comprehensive**: Tracks everything from functions to API calls
4. **Real-Time**: Live dashboard with auto-refresh capabilities
5. **Export Ready**: JSON/CSV exports for further analysis
6. **Production Safe**: Minimal overhead, can be enabled/disabled anytime

## No-Code Setup

### Method 1: Programmatic Setup

```python
from praisonaiagents import (
    enable_performance_monitoring,
    enable_auto_instrumentation
)

# One-time setup - no changes to existing code needed
enable_performance_monitoring()
enable_auto_instrumentation()

# Your existing PraisonAI code works unchanged
agent = Agent(name="MyAgent", role="Helper")
result = agent.chat("Analyze this data...")
```

### Method 2: Environment Variables

```bash
# Set environment variable
export PRAISONAI_PERFORMANCE_MONITORING=true
export PRAISONAI_AUTO_INSTRUMENT=true

# Run your existing Python script - no changes needed
python my_existing_script.py
```

### Method 3: CLI Wrapper

```bash
# Wrap your existing script with performance monitoring
praisonai-perf enable --auto-instrument
python my_existing_script.py
praisonai-perf summary
```

## Performance Analysis

### Function-Level Analysis

```python
from praisonaiagents import get_performance_monitor

monitor = get_performance_monitor()

# Get metrics for all functions
function_metrics = monitor.get_function_metrics()
for func_name, metrics in function_metrics.items():
    print(f"{func_name}:")
    print(f"  Total calls: {metrics['total_calls']}")
    print(f"  Average time: {metrics['average_time']:.3f}s")
    print(f"  Total time: {metrics['total_time']:.3f}s")

# Get metrics for specific function
specific_metrics = monitor.get_function_metrics("Agent.chat")
print(f"Agent.chat average time: {specific_metrics['average_time']:.3f}s")
```

### API Call Analysis

```python
# Analyze all API calls
api_metrics = monitor.get_api_metrics()
print(f"Total API calls: {api_metrics['total_calls']}")
print(f"Success rate: {api_metrics['success_rate']:.1%}")
print(f"Average response time: {api_metrics['average_time']:.3f}s")

# Analyze by provider
for provider, stats in api_metrics['by_provider'].items():
    print(f"{provider}: {stats['count']} calls, {stats['average_time']:.3f}s avg")

# Filter by API type
llm_metrics = monitor.get_api_metrics('llm')
http_metrics = monitor.get_api_metrics('http')
```

### Execution Flow Analysis

```python
# Get call hierarchy
hierarchy = monitor.get_call_hierarchy(max_depth=3)

def print_hierarchy(calls, depth=0):
    for call in calls:
        indent = "  " * depth
        status = "✅" if call['success'] else "❌"
        print(f"{indent}{status} {call['function']} ({call['duration']:.3f}s)")
        print_hierarchy(call.get('children', []), depth + 1)

print_hierarchy(hierarchy['call_hierarchy'])
```

## Web Dashboard

The web dashboard provides real-time visualization of performance metrics.

### Starting the Dashboard

```python
from praisonaiagents import start_performance_dashboard

# Start dashboard on custom port
url = start_performance_dashboard(port=8889)
print(f"Dashboard available at: {url}")

# Dashboard features:
# - Real-time performance metrics
# - Function performance tables
# - API call analysis
# - Memory usage graphs
# - Call hierarchy visualization
# - Auto-refresh every 10 seconds
```

### Dashboard Features

- **System Overview**: Monitoring status, session duration, memory usage
- **Performance Summary**: Function calls, API calls, execution times
- **Function Analysis**: Slowest functions with detailed metrics
- **API Monitoring**: API call performance by provider
- **Call Hierarchy**: Visual execution flow tree
- **Auto-Refresh**: Live updates every 10 seconds

## CLI Tools

### Available Commands

```bash
# Enable/disable monitoring
praisonai-perf enable --auto-instrument
praisonai-perf disable --restore-functions

# Status and monitoring
praisonai-perf status
praisonai-perf summary --json

# Function analysis
praisonai-perf functions --top 10
praisonai-perf functions --function "Agent.chat" --json

# API analysis
praisonai-perf apis --type llm
praisonai-perf apis --json

# Call hierarchy
praisonai-perf hierarchy --depth 5

# Dashboard management
praisonai-perf dashboard --port 8888
praisonai-perf dashboard --stop

# Data management
praisonai-perf export --output metrics.json
praisonai-perf clear --confirm

# Reports
praisonai-perf report --output report.txt --format text
```

### Example CLI Workflow

```bash
# 1. Enable monitoring for existing project
cd my_praisonai_project/
praisonai-perf enable --auto-instrument

# 2. Run your application (no changes needed)
python my_app.py

# 3. Analyze performance
praisonai-perf summary
praisonai-perf functions --top 5

# 4. Start dashboard for real-time monitoring
praisonai-perf dashboard --port 8888 &

# 5. Export data for reporting
praisonai-perf export --output daily_metrics.json

# 6. Generate text report
praisonai-perf report --output performance_report.txt
```

## API Reference

### Core Functions

```python
from praisonaiagents import (
    get_performance_monitor,
    enable_performance_monitoring,
    disable_performance_monitoring,
    enable_auto_instrumentation,
    disable_auto_instrumentation,
    start_performance_dashboard,
    stop_performance_dashboard
)

# Get monitor instance
monitor = get_performance_monitor()

# Enable/disable monitoring
enable_performance_monitoring()
disable_performance_monitoring()

# Auto-instrumentation (monkey patching)
enable_auto_instrumentation()  # Track all PraisonAI functions
disable_auto_instrumentation()  # Restore original functions

# Dashboard
url = start_performance_dashboard(port=8888)
stop_performance_dashboard()
```

### PerformanceMonitor Class

```python
monitor = get_performance_monitor()

# Configuration
monitor.enable()
monitor.disable()
monitor.is_enabled()  # Returns bool

# Metrics retrieval
summary = monitor.get_performance_summary()
function_metrics = monitor.get_function_metrics(function_name=None)
api_metrics = monitor.get_api_metrics(api_type=None)
hierarchy = monitor.get_call_hierarchy(max_depth=5)

# Data management
json_data = monitor.export_metrics('json', filepath=None)
monitor.clear_metrics()

# Manual tracking (if needed)
with monitor.track_function("my_function", "my_module"):
    # Your code here
    pass
```

### Decorators for Custom Functions

```python
from praisonaiagents import track_function_performance, track_api_performance

@track_function_performance("custom_function")
def my_custom_function():
    # This function will be tracked
    pass

# Track API calls manually
with track_api_performance("llm", "openai", "POST", "openai", "gpt-4"):
    # API call code
    pass
```

## Examples

### Example 1: Basic Monitoring

```python
from praisonaiagents import Agent, enable_performance_monitoring, enable_auto_instrumentation

# Enable monitoring
enable_performance_monitoring()
enable_auto_instrumentation()

# Use PraisonAI normally
agent = Agent(name="TestAgent", role="Assistant")
response = agent.chat("What is machine learning?")

# Get insights
from praisonaiagents import get_performance_monitor
monitor = get_performance_monitor()
print(monitor.get_performance_summary())
```

### Example 2: Multi-Agent Workflow Analysis

```python
from praisonaiagents import Agent, PraisonAIAgents, Task
from praisonaiagents import enable_performance_monitoring, enable_auto_instrumentation

# Enable monitoring
enable_performance_monitoring()
enable_auto_instrumentation()

# Create multi-agent workflow
researcher = Agent(name="Researcher", role="Research Specialist")
writer = Agent(name="Writer", role="Content Writer")

research_task = Task(description="Research AI trends", agent=researcher)
writing_task = Task(description="Write article", agent=writer, context=[research_task])

workflow = PraisonAIAgents(
    agents=[researcher, writer],
    tasks=[research_task, writing_task],
    process="sequential"
)

result = workflow.start()

# Analyze performance
monitor = get_performance_monitor()
hierarchy = monitor.get_call_hierarchy()
api_metrics = monitor.get_api_metrics()

print(f"Workflow completed with {api_metrics['total_calls']} API calls")
```

### Example 3: Production Monitoring

```python
import atexit
from praisonaiagents import (
    enable_performance_monitoring,
    enable_auto_instrumentation,
    get_performance_monitor
)

def setup_production_monitoring():
    """Setup monitoring for production environment."""
    enable_performance_monitoring()
    enable_auto_instrumentation()
    
    def save_metrics_on_exit():
        monitor = get_performance_monitor()
        metrics = monitor.export_metrics('json', 'production_metrics.json')
        print("Performance metrics saved to production_metrics.json")
    
    atexit.register(save_metrics_on_exit)

# Call at start of your application
setup_production_monitoring()

# Your existing PraisonAI application code
# ... no changes needed ...
```

## Performance Optimization Workflow

### 1. Establish Baseline

```python
from praisonaiagents import get_performance_monitor

monitor = get_performance_monitor()
monitor.clear_metrics()  # Start fresh

# Run your typical workflow
# ... your code ...

baseline = monitor.get_performance_summary()
print(f"Baseline: {baseline['total_execution_time']:.3f}s total")
```

### 2. Identify Bottlenecks

```python
# Find slowest functions
function_metrics = monitor.get_function_metrics()
slowest = sorted(
    function_metrics.items(),
    key=lambda x: x[1]['average_time'],
    reverse=True
)[:5]

print("Top 5 slowest functions:")
for func_name, metrics in slowest:
    impact = metrics['average_time'] * metrics['total_calls']
    print(f"{func_name}: {metrics['average_time']:.3f}s avg (impact: {impact:.3f}s)")
```

### 3. Analyze API Performance

```python
api_metrics = monitor.get_api_metrics()
print(f"API Success Rate: {api_metrics['success_rate']:.1%}")
print(f"Average API Response: {api_metrics['average_time']:.3f}s")

# Check for slow providers
for provider, stats in api_metrics['by_provider'].items():
    if stats['average_time'] > 2.0:
        print(f"⚠️ Slow provider detected: {provider} ({stats['average_time']:.3f}s avg)")
```

### 4. Generate Optimization Report

```python
def generate_optimization_report():
    monitor = get_performance_monitor()
    summary = monitor.get_performance_summary()
    
    report = []
    report.append("# Performance Optimization Report")
    report.append(f"Generated: {datetime.now()}")
    
    # Function recommendations
    slowest_functions = summary.get('slowest_functions', [])[:3]
    if slowest_functions:
        report.append("\n## Function Optimization Opportunities")
        for func in slowest_functions:
            if func['average_time'] > 1.0:
                report.append(f"- Optimize `{func['function']}`: {func['average_time']:.3f}s average")
    
    # API recommendations
    api_metrics = monitor.get_api_metrics()
    if api_metrics and api_metrics['average_time'] > 2.0:
        report.append("\n## API Optimization Opportunities")
        report.append(f"- Consider API caching (current avg: {api_metrics['average_time']:.3f}s)")
    
    return "\n".join(report)

print(generate_optimization_report())
```

## Troubleshooting

### Common Issues

#### 1. No Performance Data Collected

```python
from praisonaiagents import get_performance_monitor

monitor = get_performance_monitor()
if not monitor.is_enabled():
    print("❌ Performance monitoring is disabled")
    monitor.enable()
    print("✅ Performance monitoring enabled")

# Check if auto-instrumentation is working
summary = monitor.get_performance_summary()
if summary['total_function_calls'] == 0:
    print("⚠️ No function calls tracked - enable auto-instrumentation")
    from praisonaiagents import enable_auto_instrumentation
    enable_auto_instrumentation()
```

#### 2. Dashboard Won't Start

```python
from praisonaiagents import start_performance_dashboard

# Try different port
url = start_performance_dashboard(port=8889)
if not url:
    print("❌ Failed to start dashboard")
    print("Try: pip install 'praisonaiagents[dashboard]'")
else:
    print(f"✅ Dashboard started at {url}")
```

#### 3. High Memory Usage

```python
monitor = get_performance_monitor()

# Check memory usage
summary = monitor.get_performance_summary()
memory_mb = summary.get('memory_usage', {}).get('rss_mb', 0)

if memory_mb > 1000:  # More than 1GB
    print(f"⚠️ High memory usage: {memory_mb}MB")
    # Clear old data
    monitor.clear_metrics()
    print("✅ Performance data cleared")
```

#### 4. Restore Original Functions

```python
from praisonaiagents import disable_auto_instrumentation

# If you need to restore original function behavior
disable_auto_instrumentation()
print("✅ Original functions restored")
```

### Environment Variables

```bash
# Disable performance monitoring
export PRAISONAI_PERFORMANCE_MONITORING=false

# Enable debug logging
export LOGLEVEL=DEBUG

# Set custom dashboard port
export PRAISONAI_DASHBOARD_PORT=8888
```

### Best Practices

1. **Production Use**: Enable monitoring for production systems to identify real-world bottlenecks
2. **Memory Management**: Clear metrics periodically with `monitor.clear_metrics()`
3. **Selective Monitoring**: Use function-specific tracking for targeted analysis
4. **Regular Exports**: Save metrics to files for historical analysis
5. **Dashboard Monitoring**: Use the web dashboard for real-time monitoring during development

## Advanced Usage

### Custom Instrumentation

```python
from praisonaiagents import get_performance_monitor

monitor = get_performance_monitor()

# Manual function tracking
with monitor.track_function("custom_operation", "my_module"):
    # Your custom code
    expensive_operation()

# Custom API tracking
call_id = monitor.track_api_call("custom_api", "my-service", "POST")
try:
    result = my_api_call()
    monitor.complete_api_call(call_id, success=True)
except Exception as e:
    monitor.complete_api_call(call_id, success=False, error=str(e))
```

### Integration with Monitoring Systems

```python
import json
from praisonaiagents import get_performance_monitor

def export_to_prometheus():
    """Export metrics to Prometheus format."""
    monitor = get_performance_monitor()
    metrics = monitor.get_function_metrics()
    
    prometheus_metrics = []
    for func_name, stats in metrics.items():
        prometheus_metrics.append(
            f'praisonai_function_duration{{function="{func_name}"}} {stats["average_time"]}'
        )
        prometheus_metrics.append(
            f'praisonai_function_calls_total{{function="{func_name}"}} {stats["total_calls"]}'
        )
    
    return "\n".join(prometheus_metrics)

def export_to_cloudwatch():
    """Export metrics to AWS CloudWatch."""
    import boto3
    
    monitor = get_performance_monitor()
    summary = monitor.get_performance_summary()
    
    cloudwatch = boto3.client('cloudwatch')
    cloudwatch.put_metric_data(
        Namespace='PraisonAI/Performance',
        MetricData=[
            {
                'MetricName': 'FunctionCalls',
                'Value': summary['total_function_calls'],
                'Unit': 'Count'
            },
            {
                'MetricName': 'ExecutionTime',
                'Value': summary['total_execution_time'],
                'Unit': 'Seconds'
            }
        ]
    )
```

This comprehensive performance monitoring system provides everything you need to analyze, optimize, and monitor your PraisonAI applications without making any changes to your existing code.