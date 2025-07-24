# PraisonAI Performance Monitoring Examples

This directory contains comprehensive examples demonstrating various performance monitoring approaches for PraisonAI Agents without modifying existing code.

## 📁 Directory Structure

```
monitoring/
├── basic/                   # Simple monitoring examples
│   ├── simple_agent_monitoring.py
│   └── task_timing_metrics.py
├── advanced/               # Complex monitoring implementations  
│   └── comprehensive_session_monitoring.py
├── integration/           # Integration with external systems
│   └── monitoring_integrations.py
├── telemetry/            # Telemetry-specific examples
│   └── telemetry_integration.py
└── README.md            # This file
```

## 🚀 Quick Start

All examples are self-contained and can be run independently:

```bash
# Basic agent monitoring
python examples/monitoring/basic/simple_agent_monitoring.py

# Task timing and metrics
python examples/monitoring/basic/task_timing_metrics.py

# Advanced session monitoring
python examples/monitoring/advanced/comprehensive_session_monitoring.py

# Telemetry integration
python examples/monitoring/telemetry/telemetry_integration.py

# External integrations
python examples/monitoring/integration/monitoring_integrations.py
```

## 📊 Monitoring Options Overview

### 1. Basic Monitoring (`basic/`)

**Simple Agent Monitoring** (`simple_agent_monitoring.py`)
- ✅ Enable metrics with `track_metrics=True`
- ✅ Access metrics via `agent.last_metrics`
- ✅ Session-level aggregation with `MetricsCollector`
- ✅ Basic performance reporting

**Task Timing & Metrics** (`task_timing_metrics.py`)
- ✅ Manual performance metrics creation
- ✅ Context managers for automatic timing
- ✅ Token metrics aggregation
- ✅ Custom timing measurements
- ✅ Metrics export to files

### 2. Advanced Monitoring (`advanced/`)

**Comprehensive Session Monitoring** (`comprehensive_session_monitoring.py`)
- ✅ Multi-agent session tracking
- ✅ Real-time performance monitoring
- ✅ Automated performance alerts
- ✅ Live monitoring dashboard
- ✅ Agent performance rankings
- ✅ Comprehensive analytics and reporting
- ✅ Export capabilities (JSON + summary)

### 3. Telemetry Integration (`telemetry/`)

**Telemetry Integration** (`telemetry_integration.py`)
- ✅ Automatic telemetry tracking
- ✅ PostHog integration for analytics
- ✅ Custom event tracking
- ✅ Environment-based configuration
- ✅ Debug logging for development
- ✅ Session-level data aggregation

### 4. External Integrations (`integration/`)

**Monitoring Integrations** (`monitoring_integrations.py`)
- ✅ SQLite database logging
- ✅ Webhook notifications with cooldowns
- ✅ Real-time HTTP dashboard
- ✅ Configurable performance alerts
- ✅ API endpoints for metrics
- ✅ Multi-system integration

## 🔧 Configuration Options

### Environment Variables

```bash
# Disable telemetry completely
export PRAISONAI_TELEMETRY_DISABLED=true

# Enable PostHog integration
export POSTHOG_API_KEY=your_posthog_key

# Enable debug logging
export LOGLEVEL=DEBUG
```

### Agent Configuration

```python
# Basic monitoring
agent = Agent(
    name="MyAgent",
    role="Data Analyst",
    track_metrics=True  # Enable monitoring
)

# Custom metrics collector
collector = MetricsCollector()
agent = Agent(
    name="MyAgent",
    role="Data Analyst", 
    track_metrics=True,
    metrics_collector=collector  # Use shared collector
)
```

### Performance Thresholds

```python
# Configure custom performance alerts
performance_thresholds = {
    'max_ttft': 2.0,           # Maximum Time To First Token (seconds)
    'min_tokens_per_sec': 10.0, # Minimum tokens per second
    'max_total_time': 30.0     # Maximum total execution time (seconds)
}
```

## 📈 Metrics Available

### Token Metrics
- **Input Tokens**: Tokens in the prompt/input
- **Output Tokens**: Tokens in the generated response
- **Total Tokens**: Combined input + output tokens
- **Cached Tokens**: Tokens retrieved from cache
- **Reasoning Tokens**: Tokens used for internal reasoning
- **Audio Tokens**: Tokens for audio processing (if applicable)

### Performance Metrics
- **Time To First Token (TTFT)**: Time until first token is generated
- **Total Time**: Complete execution time
- **Tokens Per Second (TPS)**: Generation speed
- **Request Count**: Number of requests processed

### Session Metrics
- **Session ID**: Unique session identifier
- **Duration**: Total session duration
- **Agent Metrics**: Per-agent token and performance statistics
- **Model Metrics**: Per-model usage statistics
- **Performance Rankings**: Agent performance comparisons

## 🎯 Use Cases & Scenarios

### 1. Development & Debugging
- **Use**: `basic/simple_agent_monitoring.py`
- **Benefits**: Quick performance insights, debug slow responses
- **Setup**: Just add `track_metrics=True` to your agents

### 2. Production Monitoring
- **Use**: `advanced/comprehensive_session_monitoring.py`
- **Benefits**: Real-time alerts, performance tracking, trend analysis
- **Setup**: Implement monitoring session wrapper

### 3. Analytics & Insights
- **Use**: `telemetry/telemetry_integration.py`
- **Benefits**: Long-term trends, usage patterns, optimization insights
- **Setup**: Configure PostHog integration

### 4. Enterprise Integration
- **Use**: `integration/monitoring_integrations.py`
- **Benefits**: Database logging, webhook alerts, custom dashboards
- **Setup**: Implement database and webhook handlers

## 🏆 Best Practices

### 1. **Choose the Right Level**
```python
# Development: Basic monitoring
agent = Agent(name="DevAgent", track_metrics=True)

# Production: Session-level monitoring
collector = MetricsCollector()
agents = [
    Agent(name="Agent1", track_metrics=True, metrics_collector=collector),
    Agent(name="Agent2", track_metrics=True, metrics_collector=collector)
]

# Enterprise: Full integration
monitoring_system = IntegratedMonitoringSystem("Production")
```

### 2. **Performance Thresholds**
```python
# Set realistic thresholds based on your use case
thresholds = {
    'max_ttft': 1.0,      # Interactive: < 1s
    'max_ttft': 3.0,      # Batch processing: < 3s  
    'min_tokens_per_sec': 20.0,  # High-performance: > 20 TPS
    'min_tokens_per_sec': 5.0,   # Standard: > 5 TPS
}
```

### 3. **Export & Analysis**
```python
# Regular exports for analysis
collector.export_metrics(f"metrics_{datetime.now().strftime('%Y%m%d')}.json")

# Database logging for long-term storage
db_logger = DatabaseLogger()
db_logger.log_agent_metrics(session_id, agent_name, task, tokens, perf)
```

### 4. **Alert Management**
```python
# Configure cooldowns to prevent alert spam
alert_config = AlertConfig(
    name="high_latency",
    condition=lambda data: data['ttft'] > 2.0,
    cooldown_seconds=300  # 5-minute cooldown
)
```

## 🔍 Troubleshooting

### Common Issues

1. **No metrics collected**
   - ✅ Ensure `track_metrics=True` on agents
   - ✅ Check if telemetry is disabled: `PRAISONAI_TELEMETRY_DISABLED`

2. **PostHog integration not working**
   - ✅ Set `POSTHOG_API_KEY` environment variable
   - ✅ Check network connectivity
   - ✅ Enable debug logging: `LOGLEVEL=DEBUG`

3. **Database logging fails**
   - ✅ Check write permissions for database file
   - ✅ Ensure SQLite is available
   - ✅ Verify database schema initialization

4. **Dashboard not accessible**
   - ✅ Check if port 8080 is available
   - ✅ Verify HTTP server started successfully
   - ✅ Check firewall settings

### Debug Logging

```bash
# Enable verbose logging
export LOGLEVEL=DEBUG
python your_monitoring_script.py

# Look for telemetry debug messages:
# "Token usage tracked: 150 total tokens"
# "Performance tracked: TTFT=0.250s, TPS=45.2"
```

## 📚 Additional Resources

### Code Examples
- All examples include detailed comments and documentation
- Each example can be run independently
- Progressive complexity from basic to advanced

### Integration Guides
- **Database Integration**: SQLite schema and queries
- **Webhook Integration**: Payload formats and error handling  
- **Dashboard Integration**: HTTP server and API endpoints
- **Alert Configuration**: Threshold setting and cooldown management

### Performance Optimization
- Monitor token usage to optimize prompts
- Track TTFT to identify bottlenecks
- Use TPS metrics to compare model performance
- Analyze cache hit ratios for efficiency gains

## 🤝 Contributing

Found an issue or want to add more monitoring examples?

1. **Report Issues**: Create GitHub issues for bugs or feature requests
2. **Add Examples**: Contribute new monitoring scenarios
3. **Improve Documentation**: Help make examples clearer
4. **Share Use Cases**: Document your monitoring implementations

---

## 💡 Key Takeaways

1. **Start Simple**: Begin with `track_metrics=True` for basic monitoring
2. **Scale Gradually**: Add session-level monitoring as needed
3. **Integrate Wisely**: Connect to your existing monitoring infrastructure
4. **Monitor Continuously**: Set up alerts and regular reporting
5. **Optimize Based on Data**: Use metrics to improve performance

Happy monitoring! 🚀📊