# PraisonAI Performance Monitoring Examples

This directory contains 10 comprehensive examples demonstrating how to integrate performance monitoring with PraisonAI agents. Each example builds upon the basic pattern while showcasing different aspects of the monitoring system.

## 🚀 Quick Start

All examples follow this basic pattern:

```python
from praisonaiagents import Agent
from praisonaiagents.telemetry import monitor_function, track_api_call

@monitor_function("my_function")
def my_function():
    # Your function code here
    pass

agent = Agent(
    instructions="You are a helpful assistant",
    llm="gpt-4o-mini"
)

with track_api_call("agent_request"):
    result = agent.start("Your question here")
```

## 📊 Examples Overview

### 1. Basic Agent with Monitoring (`01_basic_agent_with_monitoring.py`)
**Purpose:** Introduction to performance monitoring fundamentals
- Function execution timing with `@monitor_function` decorator
- API call tracking with `track_api_call` context manager
- Basic performance statistics retrieval

### 2. Multi-Agent Workflow Monitoring (`02_multi_agent_workflow_monitoring.py`)
**Purpose:** Monitor complex multi-agent systems
- Multiple agents with different roles
- Inter-agent communication tracking
- Workflow performance analysis
- Task delegation timing

### 3. Agent with Tools Monitoring (`03_agent_with_tools_monitoring.py`)
**Purpose:** Monitor performance when using external tools
- Tool execution timing
- Search operation performance
- Tool call success/failure tracking
- Tool usage analysis

### 4. Async Agent Monitoring (`04_async_agent_monitoring.py`)
**Purpose:** Performance monitoring in asynchronous workflows
- Async function execution timing
- Concurrent task performance
- Async API call tracking
- Parallel operation analysis

### 5. Error Handling Monitoring (`05_error_handling_monitoring.py`)
**Purpose:** Monitor performance during error scenarios
- Error rate tracking
- Failed operation timing
- Recovery mechanism performance
- Exception handling with monitoring

### 6. Memory Agent Monitoring (`06_memory_agent_monitoring.py`)
**Purpose:** Monitor stateful agents with memory
- Memory storage and retrieval timing
- Knowledge base operations
- Session persistence performance
- Memory search optimization

### 7. Hierarchical Agents Monitoring (`07_hierarchical_agents_monitoring.py`)
**Purpose:** Monitor complex organizational agent structures
- Manager-worker agent relationships
- Task delegation timing
- Hierarchical decision making performance
- Cross-level communication monitoring

### 8. Custom Tools Monitoring (`08_custom_tools_monitoring.py`)
**Purpose:** Monitor performance with custom-built tools
- Custom tool execution timing
- Tool creation and registration performance
- Tool usage pattern analysis
- Tool efficiency optimization

### 9. Streaming Monitoring (`09_streaming_monitoring.py`)
**Purpose:** Monitor real-time and streaming operations
- Real-time performance tracking
- Streaming response monitoring
- Live performance metrics
- Continuous performance analysis

### 10. Comprehensive Dashboard (`10_comprehensive_dashboard.py`)
**Purpose:** Complete performance monitoring solution
- Advanced analytics and reporting
- Performance trends and insights
- System-wide monitoring overview
- Executive dashboard with health scores

## 🎯 Key Monitoring Features Demonstrated

### Core Monitoring Tools
- **`@monitor_function(name)`** - Decorates functions for timing and statistics
- **`track_api_call(name)`** - Context manager for API call monitoring
- **`get_performance_report()`** - Generate comprehensive performance reports
- **`get_function_stats()`** - Retrieve detailed function performance data
- **`get_api_stats()`** - Get API call performance metrics

### Advanced Analytics
- **`analyze_function_flow()`** - Analyze execution flow and bottlenecks
- **`visualize_execution_flow()`** - Generate flow visualization
- **`analyze_performance_trends()`** - Identify performance trends
- **`generate_comprehensive_report()`** - Complete analysis with recommendations

### Performance Metrics Tracked
- **Execution Time:** Min, max, average, and total execution times
- **Call Counts:** Number of function calls and API requests
- **Error Rates:** Success/failure ratios and error tracking
- **Throughput:** Operations per second and message processing rates
- **Flow Analysis:** Function call chains and execution patterns

## 📈 Usage Patterns

### Basic Monitoring Pattern
```python
@monitor_function("function_name")
def your_function():
    # Function implementation
    pass

with track_api_call("api_operation"):
    result = some_api_call()
```

### Performance Analysis Pattern
```python
# After running monitored operations
stats = get_function_stats()
report = get_performance_report()
trends = analyze_performance_trends()
```

### Real-time Monitoring Pattern
```python
# For streaming or real-time operations
while streaming_active:
    with track_api_call("stream_message"):
        process_message()
    
    # Check performance in real-time
    current_stats = performance_monitor.get_function_performance()
```

## 🔍 Performance Insights

Each example provides insights into different aspects:

- **Response Times:** How fast your agents respond
- **Bottlenecks:** Where delays occur in your workflow
- **Error Patterns:** What fails and how often
- **Resource Usage:** Efficiency of different operations
- **Scaling Behavior:** How performance changes with load

## 🚀 Running the Examples

1. **Install PraisonAI with performance monitoring support:**
   ```bash
   pip install praisonaiagents
   ```

2. **Set up your environment:**
   ```bash
   export OPENAI_API_KEY="your-api-key-here"
   # or
   export ANTHROPIC_API_KEY="your-anthropic-key-here"
   ```

3. **Run any example:**
   ```bash
   python 01_basic_agent_with_monitoring.py
   python 10_comprehensive_dashboard.py
   ```

## 📊 Sample Output

Each example provides detailed performance output like:

```
📊 PERFORMANCE MONITORING RESULTS
==================================================
📈 Function Performance Statistics:
  question_processing:
    Calls: 1
    Avg Time: 0.100s
    Total Time: 0.100s
  agent_execution:
    Calls: 1
    Avg Time: 1.250s
    Total Time: 1.250s

🌐 API Call Performance:
  sky_explanation_request:
    Success Rate: 100.0%
    Average Response Time: 1.200s
    Total Calls: 1
```

## 💡 Best Practices

1. **Strategic Monitoring:** Don't monitor everything - focus on critical paths
2. **Performance Baselines:** Establish baseline metrics for comparison
3. **Error Handling:** Always monitor error rates alongside performance
4. **Real-time Analysis:** Use streaming monitoring for production systems
5. **Regular Reviews:** Analyze trends and patterns regularly

## 🔧 Customization

You can customize monitoring by:

- **Custom Metrics:** Add your own performance counters
- **Alert Thresholds:** Set up alerts for performance degradation
- **Export Data:** Export performance data to external monitoring systems
- **Dashboard Integration:** Build custom dashboards using the monitoring APIs

## 📚 Further Reading

- [PraisonAI Documentation](https://docs.praisonai.com)
- [Performance Monitoring Guide](../../../src/praisonai-agents/praisonaiagents/telemetry/README.md)
- [API Reference](../../../src/praisonai-agents/praisonaiagents/telemetry/__init__.py)

## 🤝 Contributing

These examples are designed to be educational and extensible. Feel free to:
- Add new monitoring scenarios
- Improve existing examples
- Share your performance optimization discoveries

---

**Note:** Performance monitoring is optional and can be disabled by setting `PRAISONAI_TELEMETRY_DISABLED=true` if needed.