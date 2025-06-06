# Workflows Avançados: Agentes Multimodais

Agentes multimodais conseguem lidar com diferentes tipos de dados, como texto e imagens, dentro do mesmo fluxo de trabalho. No PraisonAI, você pode combinar ferramentas de visão computacional com seus agentes tradicionais.

```python
from praisonaiagents import Agent
from praisonaiagents.tools import image_to_text

agent = Agent(tools=[image_to_text])
agent.start("Analyze the image at example.png and summarise it")
```

Utilize esse padrão quando precisar de entradas visuais ou de outros formatos além de texto.
