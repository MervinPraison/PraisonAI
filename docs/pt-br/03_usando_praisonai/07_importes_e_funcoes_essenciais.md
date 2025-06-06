
# Importações e Funções Essenciais

Esta lição apresenta as importações mais comuns do PraisonAI para criar agentes e fluxos de trabalho. Use-a como referência rápida ao iniciar seus projetos.

## Principais Módulos

```python
from praisonaiagents import Agent, Task, PraisonAIAgents, Tools
from praisonaiagents.utils import get_logger
```

- `Agent` define o comportamento de um agente individual.
- `Task` encapsula uma unidade de trabalho executável por um agente.
- `PraisonAIAgents` orquestra múltiplos agentes e tarefas.
- `Tools` dá acesso ao catálogo de ferramentas internas.
- `get_logger` cria um logger padronizado para acompanhar a execução.

## Exemplo Rápido

```python
from praisonaiagents import Agent, Task, PraisonAIAgents, Tools
from praisonaiagents.utils import get_logger

logger = get_logger()

# Define a tarefa
minha_tarefa = Task(
    description="Gerar resumo do texto",
    tools=[Tools.SEARCH]
)

# Define o agente
meu_agente = Agent(
    role="Escritor",
    goal="Produzir conteúdo de qualidade",
    tasks=[minha_tarefa]
)

# Cria o orquestrador e executa
workflow = PraisonAIAgents(agents=[meu_agente], logger=logger)
workflow.run()
```

O código acima demonstra como importar e iniciar rapidamente um fluxo simples com um único agente e uma tarefa.
=======
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

