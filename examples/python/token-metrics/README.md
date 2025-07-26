# Token Metrics Tracking Examples

This directory contains comprehensive examples demonstrating how to use PraisonAI's token metrics tracking system. These examples show you how to monitor, analyze, and optimize token usage in your agent workflows.

## 🚀 Quick Start

All examples are self-contained and can be run independently:

```bash
python 01_basic_token_tracking.py
```

## 📋 Examples Overview

### 1. Basic Token Tracking (`01_basic_token_tracking.py`)
**Level:** Beginner  
**Purpose:** Introduction to token metrics tracking  

**What you'll learn:**
- How to access basic token usage information
- Understanding input vs output tokens
- Simple workflow monitoring

**Use cases:**
- First-time users wanting to understand token consumption
- Basic cost monitoring for simple workflows
- Quick usage checks

### 2. Session Metrics (`02_session_metrics.py`)
**Level:** Intermediate  
**Purpose:** Multi-agent and multi-task token tracking  

**What you'll learn:**
- Tracking tokens across multiple agents
- Model-specific usage breakdown
- Agent-specific usage analysis
- Using the built-in display methods

**Use cases:**
- Complex workflows with multiple agents
- Comparing agent efficiency
- Session-level analytics

### 3. Cost Estimation (`03_cost_estimation.py`)
**Level:** Intermediate  
**Purpose:** Detailed cost analysis and budgeting  

**What you'll learn:**
- Converting token usage to cost estimates
- Custom pricing model integration
- Cost optimization strategies
- Budget planning techniques

**Use cases:**
- Production cost monitoring
- Budget planning and forecasting
- Cost optimization initiatives
- Financial reporting

### 4. Telemetry Integration (`04_telemetry_integration.py`)
**Level:** Advanced  
**Purpose:** Integration with monitoring and analytics systems  

**What you'll learn:**
- Exporting metrics for external analysis
- Privacy-first tracking principles
- Pattern analysis for optimization
- Integration with observability stacks

**Use cases:**
- Enterprise monitoring setups
- Business intelligence integration
- Automated reporting systems
- Performance analytics

### 5. Advanced Agent Integration (`05_advanced_agent_integration.py`)
**Level:** Advanced  
**Purpose:** Production-ready monitoring and optimization  

**What you'll learn:**
- Real-time token budget management
- Multi-model efficiency comparison
- Task-level performance analysis
- Advanced optimization techniques

**Use cases:**
- Production environment monitoring
- Performance optimization projects
- Resource allocation planning
- Advanced analytics

## 🔧 Setup Requirements

### Basic Requirements
```bash
pip install praisonaiagents
```

### Environment Variables
Set up your LLM provider API keys:

```bash
# For OpenAI
export OPENAI_API_KEY="your-api-key"

# For other providers, see PraisonAI documentation
```

### Optional Dependencies
For advanced examples with export functionality:
```bash
pip install json  # Usually included in Python standard library
```

## 📊 Understanding Token Metrics

### Token Types Tracked
- **Input Tokens:** Tokens in your prompts and context
- **Output Tokens:** Tokens in model responses
- **Cached Tokens:** Tokens served from cache (when supported)
- **Reasoning Tokens:** Tokens used in model reasoning (when supported)
- **Audio Tokens:** Tokens for audio input/output (when supported)

### Key Metrics
- **Total Tokens:** Sum of all token types
- **Token Ratios:** Output/Input ratios for efficiency analysis
- **Cost Estimates:** Monetary cost based on provider pricing
- **Usage Patterns:** Temporal and agent-specific patterns

## 🎯 Best Practices

### 1. Performance Optimization
- **No Overhead:** Token tracking adds minimal performance impact
- **Thread-Safe:** Safe for concurrent agent execution
- **Bounded Memory:** Automatic cleanup prevents memory leaks

### 2. Cost Management
- Set up token budgets for production workloads
- Monitor usage patterns to identify optimization opportunities
- Use cost-effective models for non-critical tasks

### 3. Monitoring Strategy
- Track both aggregate and per-agent metrics
- Set up automated alerts for unusual usage patterns
- Export metrics for historical analysis

### 4. Privacy and Security
- Token metrics contain no personal data
- Only usage statistics are tracked
- No prompt content or responses are stored
- Telemetry can be disabled if needed

## 🔍 Common Use Cases

### Development
```python
# Quick token check during development
agents = PraisonAIAgents(...)
result = agents.run()
agents.display_token_usage()  # Simple display
```

### Production Monitoring
```python
# Comprehensive monitoring setup
budget_manager = TokenBudgetManager(max_tokens=50000)
agents = PraisonAIAgents(...)

# Run with monitoring
result = agents.run()
detailed_report = agents.get_detailed_token_report()

# Export for analysis
export_metrics_to_dashboard(detailed_report)
```

### Cost Optimization
```python
# Analyze and optimize costs
summary = agents.get_token_usage_summary()
high_usage_agents = identify_high_usage(summary)
optimization_suggestions = generate_suggestions(high_usage_agents)
```

## 🚨 Troubleshooting

### Token Tracking Not Available
```python
summary = agents.get_token_usage_summary()
if "error" in summary:
    print("Token tracking not available")
    # Possible causes:
    # 1. Using unsupported LLM provider
    # 2. Missing token usage in provider response
    # 3. Telemetry disabled
```

### Zero Token Counts
- Check if your LLM provider returns usage information
- Verify API responses include token counts
- Some local models may not provide usage data

### High Token Usage
- Review prompt engineering practices
- Consider task decomposition
- Optimize context management
- Use appropriate model sizes

## 📚 Additional Resources

- [PraisonAI Documentation](https://docs.praisonai.com/)
- [Token Optimization Guide](https://docs.praisonai.com/token-optimization)
- [Cost Management Best Practices](https://docs.praisonai.com/cost-management)
- [Telemetry Configuration](https://docs.praisonai.com/telemetry)

## 🤝 Contributing

Found an issue or have an improvement suggestion?
- Open an issue on the PraisonAI GitHub repository
- Submit a pull request with your enhancement
- Share your use case in the community discussions

## 📄 License

These examples are provided under the same license as PraisonAI.

---

**Happy Token Tracking! 🎉**

For questions or support, visit the [PraisonAI Community](https://github.com/MervinPraison/PraisonAI/discussions).