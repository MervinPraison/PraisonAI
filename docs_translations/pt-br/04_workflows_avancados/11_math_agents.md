# Workflows Avançados: Math Agents

Math Agents são especializados em resolver cálculos e problemas matemáticos. Combinam o raciocínio do modelo de linguagem com ferramentas que efetuam operações precisas.

```python
from praisonaiagents import Agent
from praisonaiagents.tools import math_tool

agent = Agent(tools=[math_tool])
agent.start("Solve the equation 2*x + 3 = 9")
```

Esse padrão ajuda a garantir respostas numéricas corretas e detalhadas.
