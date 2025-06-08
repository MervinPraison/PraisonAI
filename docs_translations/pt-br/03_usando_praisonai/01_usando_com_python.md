# Usando o PraisonAI com Python (`praisonaiagents`)

A biblioteca `praisonaiagents` é o coração do PraisonAI para quem deseja construir e interagir com agentes de IA usando a linguagem Python. Ela oferece uma interface flexível e poderosa para definir agentes, suas tarefas, ferramentas e como eles colaboram.

## Configuração Inicial

Antes de começar, certifique-se de que você tem:
1.  O pacote `praisonaiagents` instalado (veja o [Guia de Instalação](./../01_instalacao/00_instalacao_windows.md)).
2.  Sua chave de API do OpenAI (ou de outro provedor de LLM suportado) configurada como uma variável de ambiente (ex: `OPENAI_API_KEY`).

## Criando um Agente Simples (Single Agent)

Um agente simples é um agente individual designado para realizar uma ou mais tarefas sem necessariamente colaborar com outros agentes.

O `README.md` principal do PraisonAI fornece um exemplo claro:

```python
from praisonaiagents import Agent

# Crie uma instância do Agente
# As instruções (instructions) são o prompt principal que define o comportamento do agente.
agente = Agent(instructions="Você é um assistente de IA prestativo.")

# Inicie o agente com uma tarefa/pergunta específica
# O método start() envia a string como a primeira tarefa/prompt para o agente.
resultado = agente.start("Escreva um roteiro de filme sobre um robô em Marte.")

print(resultado)
```

**Desmembrando o Código:**

*   `from praisonaiagents import Agent`: Importa a classe `Agent` principal.
*   `agente = Agent(instructions="...")`: Cria uma instância do agente. O parâmetro `instructions` é crucial, pois define a persona e o comportamento geral do agente. Você pode (e deve) ser muito mais específico em suas instruções para obter melhores resultados. Outros parâmetros importantes ao criar um `Agent` incluem:
    *   `role` (str): O papel do agente (ex: "Analista de Marketing").
    *   `goal` (str): O objetivo principal do agente.
    *   `backstory` (str): Uma história de fundo para dar mais contexto ao LLM.
    *   `llm` (any): Permite especificar o modelo de LLM a ser usado (ex: instâncias de modelos da OpenAI, Ollama, etc.). Se não especificado, usará um padrão (geralmente baseado em OpenAI).
    *   `tools` (list): Uma lista de [ferramentas](./../02_conceitos_fundamentais/04_ferramentas.md) que o agente pode usar.
    *   `memory` (bool): Se o agente deve usar [memória](./../02_conceitos_fundamentais/05_memoria.md).
    *   `max_iter` (int): Número máximo de iterações que o agente pode executar (útil para evitar loops infinitos).
    *   `max_rpm` (int): Número máximo de requisições por minuto (para controle de custos/limites de API).
    *   `verbose` (bool): Se deve imprimir logs detalhados da execução do agente.
    *   `allow_delegation` (bool): Se este agente pode delegar tarefas para outros agentes (relevante em sistemas multi-agente).
*   `resultado = agente.start("...")`: Este método inicia a execução do agente com a string fornecida como a primeira solicitação ou tarefa. O agente processará essa solicitação com base em suas instruções e LLM configurado.

**Exemplo Mais Detalhado (`examples/python/agents/single-agent.py`):**

O repositório PraisonAI contém exemplos mais elaborados. O arquivo `examples/python/agents/single-agent.py` mostra um agente roteirista:

```python
# (Conteúdo adaptado de examples/python/agents/single-agent.py)
from praisonaiagents import Agent
from praisonaiagents.common.log_adapter import get_logger

logger = get_logger(__name__)

# Supondo que OPENAI_API_KEY está configurada
screenwriter_agent = Agent(
    role="Roteirista Criativo",
    goal="Escrever um roteiro de filme envolvente sobre um tema específico.",
    backstory="Você é um roteirista renomado, conhecido por sua habilidade em criar narrativas cativantes e diálogos impactantes.",
    instructions="Sua tarefa é desenvolver um roteiro completo para um filme sobre robôs explorando Marte. O roteiro deve incluir descrições de cena, diálogos e desenvolvimento de personagens.",
    # llm="gpt-4", # Você pode especificar o modelo
    verbose=True,
    allow_delegation=False
)

# Para executar a tarefa principal conforme definido no 'goal' e 'instructions'
# A string passada para start() pode refinar ou iniciar a tarefa.
final_script = screenwriter_agent.start(
    "Desenvolva o roteiro sobre robôs em Marte, focando em um robô que desenvolve autoconsciência."
)

logger.info(f"Roteiro Final Gerado:\n{final_script}")
```
> **Para Rodar:** Navegue até a pasta `examples/python/agents/` no seu terminal (após clonar o repositório PraisonAI) e execute `python single-agent.py`. Certifique-se de ter suas credenciais de LLM configuradas.

## Criando Múltiplos Agentes (Multi Agents)

A verdadeira força do PraisonAI reside na capacidade de orquestrar múltiplos agentes que colaboram para resolver problemas complexos.

O `README.md` principal também ilustra isso:

```python
from praisonaiagents import Agent, PraisonAIAgents # PraisonAIAgents é o orquestrador

# Agente 1: Pesquisador
agente_pesquisador = Agent(
    instructions="Pesquise sobre os últimos avanços em Inteligência Artificial generativa.",
    role="Pesquisador de IA",
    goal="Coletar informações e artigos recentes sobre IA generativa."
    # Você pode adicionar ferramentas de busca web aqui
)

# Agente 2: Sumarizador
agente_sumarizador = Agent(
    instructions="Sumarize as descobertas do agente pesquisador de forma concisa.",
    role="Escritor Técnico",
    goal="Produzir um resumo claro e informativo baseado na pesquisa fornecida."
)

# Crie uma instância do orquestrador PraisonAIAgents
# A ordem na lista pode influenciar a execução em processos sequenciais.
sistema_multi_agente = PraisonAIAgents(
    agents=[agente_pesquisador, agente_sumarizador]
    # Você pode definir 'tasks' aqui também, ou elas podem ser inferidas
    # e passadas entre os agentes dependendo do processo.
)

# Inicie o sistema multi-agente
# O método start() do PraisonAIAgents gerenciará o fluxo entre os agentes.
# Em um processo sequencial padrão, o resultado do agente_pesquisador
# seria passado como entrada para o agente_sumarizador.
resultado_final_colaborativo = sistema_multi_agente.start()

print(resultado_final_colaborativo)
```

**Desmembrando o Código Multi-Agente:**

*   `from praisonaiagents import PraisonAIAgents`: Importa a classe que gerencia um grupo de agentes.
*   `agente_pesquisador = Agent(...)`, `agente_sumarizador = Agent(...)`: Define cada agente individualmente, com seus próprios papéis, objetivos e instruções.
*   `sistema_multi_agente = PraisonAIAgents(agents=[...])`: Cria o "time" ou sistema de agentes.
    *   O construtor de `PraisonAIAgents` pode aceitar outros parâmetros importantes, como:
        *   `tasks` (list): Uma lista de [tarefas](./../02_conceitos_fundamentais/02_tarefas.md) a serem executadas pela equipe. Se não fornecido explicitamente, o sistema pode tentar inferir ou executar um fluxo mais simples.
        *   `process` (str ou Enum): Define o [processo](./../02_conceitos_fundamentais/03_processos.md) de colaboração (ex: 'sequential', 'hierarchical'). O padrão é geralmente sequencial.
        *   `manager_llm` (any): Se estiver usando um processo hierárquico, este LLM pode ser usado pelo agente gerente.
        *   `verbose` (bool): Log detalhado.
*   `resultado_final_colaborativo = sistema_multi_agente.start()`: Inicia a colaboração. O `PraisonAIAgents` orquestra a passagem de informação (contexto) entre os agentes conforme o processo definido.

### Explorando Mais Exemplos Python

O diretório `examples/python/` no repositório PraisonAI é rico em exemplos que demonstram diversas funcionalidades:

*   **`examples/python/general/`**: Contém exemplos de conceitos como:
    *   `async_example*.py`: Execução assíncrona de agentes/tarefas.
    *   `auto_agents_example.py`: Demonstração de "Auto Agents".
    *   `example_custom_tools.py`: Como definir e usar ferramentas personalizadas.
    *   `memory_example.py` e `memory_simple.py`: Uso de memória.
    *   `workflow_example_basic.py` e `workflow_example_detailed.py`: Definição de workflows de agentes.
*   **`examples/python/agents/`**: Diferentes tipos de agentes especializados. Consulte [Modelos de Agentes](05_modelos_de_agentes.md) para um resumo de cada um.
*   **`examples/python/concepts/`**: Implementações de RAG, processamento de CSV, etc.
*   **`examples/python/usecases/`**: Soluções para casos de uso específicos como análise de sentimentos, revisão de código, etc.

**Recomendação:**
Clone o repositório PraisonAI (`git clone https://github.com/MervinPraison/PraisonAI.git`) e explore esses exemplos. Modifique-os, execute-os e veja como diferentes configurações afetam o comportamento dos agentes. Esta é uma das melhores maneiras de aprofundar seu entendimento prático.
Se surgirem problemas durante os testes, consulte a seção [Dúvidas Frequentes](../09_duvidas_frequentes.md) para possíveis soluções.

No próximo tópico, veremos como usar o PraisonAI de forma "No-Code" ou "Low-Code" através de arquivos de configuração YAML. Para um resumo rápido dos campos disponíveis, consulte [Configurações com YAML](./06_configuracoes_yaml.md).
