# Workflows Avançados: Structured Output

Em muitas aplicações, é importante que as respostas sigam um formato fixo, como JSON ou tabelas. Os agentes podem ser configurados com instruções claras para sempre retornarem dados estruturados.

```python
from praisonaiagents import Agent

agent = Agent(instructions="Answer using a JSON object with keys 'summary' and 'sources'.")
agent.start("Summarise the benefits of solar energy")
```

Definir um esquema de saída torna o pós-processamento muito mais simples.
