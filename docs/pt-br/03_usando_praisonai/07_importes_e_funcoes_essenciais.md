# Importações e Funções Essenciais para Desenvolvimento de Agentes

Esta lição apresenta os principais módulos e utilitários usados ao trabalhar com o PraisonAI em Python. Mantenha este guia à mão como referência rápida dos `imports` mais comuns.

## Classes Principais

```python
from praisonaiagents import Agent, Task, PraisonAIAgents
```

- `Agent`: cria um agente com instruções e configurações.
- `Task`: representa uma tarefa específica que pode ser atribuída a um agente.
- `PraisonAIAgents`: orquestra múltiplos agentes em um mesmo fluxo.

### Ferramentas

```python
from praisonaiagents.tools import Tool
```

Utilize a classe `Tool` (ou variações) para criar ferramentas personalizadas que expandem as capacidades do agente.

### Utilidades

```python
from praisonaiagents.common.log_adapter import get_logger
```

A função `get_logger(__name__)` fornece um logger padronizado para acompanhar a execução dos agentes e depurar eventuais problemas.

## Exemplo de Uso

```python
from praisonaiagents import Agent, Task, PraisonAIAgents
from praisonaiagents.tools import Tool
from praisonaiagents.common.log_adapter import get_logger

logger = get_logger(__name__)

researcher = Agent(instructions="Pesquise sobre IA")
summarizer = Agent(instructions="Resuma os resultados")
workflow = PraisonAIAgents(agents=[researcher, summarizer])

resultado = workflow.start("Inicie a pesquisa sobre agentes autônomos")
logger.info(resultado)
```

Este exemplo demonstra como importar as classes básicas e o logger para estruturar um fluxo simples com dois agentes.
