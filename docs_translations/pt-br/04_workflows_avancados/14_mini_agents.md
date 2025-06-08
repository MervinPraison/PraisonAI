# Workflows Avançados: Mini AI Agents

Mini Agents são versões simplificadas focadas em uma tarefa específica. Por serem leves, podem ser executados em paralelo ou incorporados a aplicações maiores com facilidade.

```python
from praisonaiagents import Agent

agent = Agent(instructions="Answer only with emoji reactions")
agent.start("How are you?")
```

São úteis quando se deseja um comportamento muito pontual sem a complexidade de um workflow completo.
