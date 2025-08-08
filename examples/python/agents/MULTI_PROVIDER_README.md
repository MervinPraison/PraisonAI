# Multi-Provider/Multi-Model Support

PraisonAI now supports intelligent multi-provider and multi-model capabilities, allowing agents to automatically select the most appropriate AI model based on task requirements, cost considerations, and performance needs.

## 🚀 Key Features

### 1. **Automatic Model Selection**
- Analyzes task complexity and selects the best model
- Considers cost vs. performance trade-offs
- Supports fallback mechanisms for reliability

### 2. **Cost Optimization**
- Routes simple tasks to cheaper models (e.g., gpt-5-nano, Gemini Flash)
- Reserves expensive models for complex tasks
- Tracks usage and provides cost estimates

### 3. **Multi-Provider Support**
- Works with OpenAI, Anthropic, Google, Groq, and more
- Seamless switching between providers
- Provider preference settings

### 4. **Flexible Routing Strategies**
- `auto`: Automatic selection based on task analysis
- `cost-optimized`: Prioritize cheaper models
- `performance-optimized`: Prioritize capability
- `manual`: Use specified model

## 📦 Installation

The multi-provider support is included in the standard installation:

```bash
pip install praisonaiagents
```

## 🔧 Basic Usage

### Simple Multi-Model Agent

```python
from praisonaiagents import Task, PraisonAIAgents
from praisonaiagents.agent import RouterAgent

# Create a multi-model agent
agent = RouterAgent(
    name="Smart Assistant",
    role="Adaptive AI Assistant",
    goal="Complete tasks using the most appropriate model",
    models=["gpt-5-nano", "gpt-5-mini", "claude-3-5-sonnet-20241022"],
    routing_strategy="auto"  # Automatic model selection
)

# Create tasks
simple_task = Task(
    name="calculate",
    description="What is 15% of 250?",
    agent=agent
)

complex_task = Task(
    name="analyze",
    description="Write a Python implementation of the A* pathfinding algorithm",
    agent=agent
)

# Run tasks - agent will automatically select appropriate models
agents = PraisonAIAgents(
    agents=[agent],
    tasks=[simple_task, complex_task]
)

results = agents.start()
```

### Cost-Optimized Workflow

```python
from praisonaiagents.llm import ModelRouter

# Create custom router with cost constraints
router = ModelRouter(
    cost_threshold=0.005,  # Max $0.005 per 1k tokens
    preferred_providers=["google", "openai"]
)

# Create cost-conscious agent
analyzer = RouterAgent(
    name="Budget Analyzer",
    role="Data Analyst",
    goal="Analyze data efficiently",
    models={
        "gemini/gemini-1.5-flash": {},
        "gpt-5-nano": {},
        "claude-3-haiku-20240307": {}
    },
    model_router=router,
    routing_strategy="cost-optimized"
)
```

## 🎯 Routing Strategies

### Auto Routing (Default)
Automatically selects models based on:
- Task complexity analysis
- Required capabilities (tools, vision, etc.)
- Context size requirements
- Cost/performance balance

### Cost-Optimized
Prioritizes cheaper models while meeting task requirements:
- Uses lightweight models for simple tasks
- Only escalates to expensive models when necessary
- Ideal for high-volume operations

### Performance-Optimized
Prioritizes model capability:
- Uses the best available model for the task
- Ideal for quality-critical applications
- Less concern for cost

### Manual
Uses the specified model without routing:
- Direct control over model selection
- Useful for testing or specific requirements

## 📊 Model Profiles

The system includes pre-configured profiles for popular models:

| Model | Provider | Best For | Cost/1k tokens |
|-------|----------|----------|----------------|
| gpt-5-nano | OpenAI | Simple tasks, speed | $0.00075 |
| gemini-1.5-flash | Google | Cost-effective, multimodal | $0.000125 |
| claude-3-haiku | Anthropic | Fast responses | $0.0008 |
| gpt-5-mini | OpenAI | General purpose | $0.0075 |
| claude-3-5-sonnet-20241022 | Anthropic | Complex reasoning | $0.009 |
| deepseek-chat | DeepSeek | Code & math | $0.0014 |

## 🔍 Task Complexity Analysis

The system analyzes tasks to determine complexity:

- **Simple**: Basic calculations, definitions, yes/no questions
- **Moderate**: Summarization, basic analysis, classification
- **Complex**: Code generation, algorithm implementation
- **Very Complex**: Multi-step reasoning, system design

## 📈 Usage Tracking

Track model usage and costs:

```python
# Get usage report
report = agent.get_usage_report()
print(report)

# Output:
{
    'agent_name': 'Smart Assistant',
    'routing_strategy': 'auto',
    'model_usage': {
        'gpt-5-nano': {'calls': 5, 'tokens': 1500, 'cost': 0.0011},
        'gpt-5-mini': {'calls': 2, 'tokens': 3000, 'cost': 0.0225}
    },
    'total_cost_estimate': 0.0236,
    'total_calls': 7
}
```

## 🛠️ Custom Model Configuration

Add custom model profiles:

```python
from praisonaiagents.llm import ModelProfile, TaskComplexity

custom_model = ModelProfile(
    name="custom-model",
    provider="custom",
    complexity_range=(TaskComplexity.SIMPLE, TaskComplexity.MODERATE),
    cost_per_1k_tokens=0.002,
    strengths=["domain-specific"],
    capabilities=["text"],
    context_window=32000
)

router = ModelRouter(models=[custom_model])
```

## 🔗 Integration with AutoAgents

Works seamlessly with AutoAgents:

```python
from praisonaiagents.agents import AutoAgents

# Create auto agents
auto = AutoAgents(
    instructions="Analyze market trends and create a report",
    max_agents=3
)

# Convert to multi-model agents
for i, agent in enumerate(auto.agents):
    auto.agents[i] = RouterAgent(
        name=agent.name,
        role=agent.role,
        goal=agent.goal,
        models=["gpt-5-nano", "gpt-5-mini", "claude-3-5-sonnet"],
        routing_strategy="auto"
    )

results = auto.start()
```

## 🌟 Best Practices

1. **Start with Auto Routing**: Let the system learn your needs
2. **Monitor Costs**: Use usage reports to optimize
3. **Set Cost Thresholds**: Prevent unexpected expenses
4. **Use Appropriate Models**: Don't use GPT-4 for simple math
5. **Leverage Fallbacks**: Configure fallback models for reliability

## 🔐 Environment Variables

Set API keys for each provider:

```bash
export OPENAI_API_KEY="sk-..."
export ANTHROPIC_API_KEY="sk-ant-..."
export GEMINI_API_KEY="..."
export GROQ_API_KEY="..."
```

## 🤝 Contributing

The multi-provider system is extensible. To add new models:

1. Add model profile to `ModelRouter.DEFAULT_MODELS`
2. Ensure the provider is supported by LiteLLM
3. Test with various task complexities

## 📚 Examples

See the complete example in `examples/python/agents/multi-provider-agent.py` for:
- Auto-routing examples
- Cost-optimized workflows
- Performance-optimized agents
- Custom routing logic
- Integration patterns

## 🎉 Benefits

- **Cost Savings**: Reduce API costs by 50-80%
- **Better Performance**: Use the right tool for each job
- **Flexibility**: Switch providers without code changes
- **Reliability**: Automatic fallbacks and error handling
- **Transparency**: Track usage and costs