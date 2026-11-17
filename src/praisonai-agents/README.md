# praisonaiagents

The lightweight core of [PraisonAI](https://github.com/MervinPraison/PraisonAI): a Python SDK for AI agents, tools, memory and multi-agent workflows. Importing it loads no LLM library; dependencies load only when a feature needs them.

```bash
pip install praisonaiagents
export OPENAI_API_KEY="your-api-key"   # or use a local model, below
```

## An agent in three lines

```python
from praisonaiagents import Agent

agent = Agent(instructions="You are a helpful assistant")
print(agent.start("Write a haiku about the sea"))
```

## Give it a tool

Any typed Python function with a docstring is a tool.

```python
from praisonaiagents import Agent

def get_weather(city: str) -> str:
    """Return the current weather for a city."""
    return f"It is sunny and 22°C in {city}."

agent = Agent(instructions="Answer weather questions", tools=[get_weather])
print(agent.start("What's the weather in Paris?"))
```

## Other models

Pass `model=`, for example `model="gpt-4o-mini"`, `model="anthropic/claude-sonnet-4-5"` or a local `model="ollama/llama3.2"` (no API key). `provider/model` names are routed through litellm: `pip install "praisonaiagents[llm]"`.

## Learn more

- [Documentation](https://praison.ai/docs): [Agents](https://praison.ai/docs/concepts/agents) · [Tools](https://praison.ai/docs/tools/tools) · [Memory](https://praison.ai/docs/concepts/memory) · [Workflows](https://praison.ai/docs/concepts/agentflow)
- `pip install praisonai` adds the terminal CLI, YAML agents, bots and the UI on top of this package.
- [Source and issues](https://github.com/MervinPraison/PraisonAI) · MIT licence
