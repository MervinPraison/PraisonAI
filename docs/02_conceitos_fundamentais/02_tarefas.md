# TODO: Translate this file to English

# Conceito Fundamental: Tarefas (Tasks)

Após entendermos o que são [Agentes](./01_agentes.md), o próximo conceito crucial no PraisonAI (e em frameworks similares como CrewAI, do qual o PraisonAI se inspira) é a **Tarefa (Task)**.

## O que é uma Tarefa?

Uma Tarefa representa uma unidade de trabalho específica e bem definida que um Agente deve realizar. Se o Agente é o "trabalhador", a Tarefa é a "ordem de serviço" ou a "descrição do trabalho" que ele precisa executar.

**Características de uma Tarefa:**

*   **Descrição Clara (Description):** Um texto detalhado que explica o que precisa ser feito, quais são os objetivos da tarefa e, possivelmente, o contexto relevante.
*   **Resultado Esperado (Expected Output):** Uma descrição do que constitui a conclusão bem-sucedida da tarefa. Isso ajuda o agente (e o sistema) a avaliar se a tarefa foi completada satisfatoriamente.
*   **Agente Responsável (Agent):** Especifica qual agente (ou tipo de agente/role) é designado para executar esta tarefa.
*   **Contexto/Dependências (Context - Opcional):** Algumas tarefas podem depender dos resultados de tarefas anteriores. O sistema gerencia a passagem desse contexto.
*   **Ferramentas (Tools - Opcional):** Pode especificar quais ferramentas o agente deve ou pode usar para realizar a tarefa, ou o agente pode decidir com base em suas ferramentas atribuídas.

## Tarefas no PraisonAI

No PraisonAI, as tarefas são o motor que impulsiona os agentes a agir. Elas fornecem o foco e a direção para o trabalho do agente.

### Como o PraisonAI Implementa Tarefas

Assim como os Agentes, as Tarefas podem ser definidas:

*   **Programaticamente (usando Python com `praisonaiagents`):**
    Você instancia a classe `Task` (ou similar, dependendo da versão e se está usando integrações como CrewAI) e define seus atributos.

    *Exemplo (conceitual, inspirado na estrutura do CrewAI que o PraisonAI integra):*
    ```python
    from praisonaiagents import Agent # Supondo que Agent e Task venham daqui ou de um módulo integrado
    # from crewai import Task # Se estiver usando a sintaxe CrewAI diretamente

    # Definindo um agente (como visto no tópico anterior)
    pesquisador = Agent(
        role='Pesquisador Sênior',
        goal='Descobrir informações de ponta sobre IA e Machine Learning',
        backstory='Você é um pesquisador renomado com anos de experiência em vasculhar artigos científicos e notícias de tecnologia.'
    )

    # Definindo uma tarefa para o agente pesquisador
    tarefa_pesquisa = { # Em PraisonAI, tarefas podem ser dicionários dentro de uma lista de tarefas do agente ou workflow
        'description': (
            "Pesquise os últimos avanços em modelos de linguagem generativa nos últimos 3 meses. "
            "Foque em novas arquiteturas, capacidades emergentes e preocupações éticas."
        ),
        'expected_output': (
            "Um relatório resumido de 3-5 parágrafos destacando os principais achados, "
            "incluindo links para as fontes primárias (artigos, posts de blog)."
        ),
        'agent': pesquisador # Associando a tarefa ao agente
    }

    # Em um workflow com múltiplos agentes, você teria uma lista de tarefas
    # e o framework orquestraria a execução.
    # Exemplo de como um agente poderia executar uma tarefa (pode variar na API exata):
    # resultado_tarefa = pesquisador.execute_task(tarefa_pesquisa)
    # print(resultado_tarefa)
    ```
    > No PraisonAI, a definição de tarefas pode ser mais integrada à configuração do Agente ou do workflow YAML, como veremos abaixo. A API exata para `Task` em Python pode depender se você está usando a camada PraisonAI nativa ou a integração CrewAI/AutoGen. Veja os exemplos em `examples/python/` para a sintaxe precisa.

*   **Declarativamente (usando arquivos YAML com `praisonai` CLI):**
    Esta é uma forma muito comum de definir tarefas no PraisonAI, especialmente ao usar múltiplos agentes.

    *Exemplo (do `agents.yaml` no README principal, focado na seção `tasks`):*
    ```yaml
    framework: praisonai
    topic: Inteligência Artificial
    roles:
      roteirista: # Nome do papel/agente
        # ... (backstory, goal, role do agente) ...
        tasks:
          tarefa_escrita_roteiro: # Nome da tarefa (identificador)
            description: "Desenvolver roteiros com personagens cativantes e diálogos sobre {topic}." # O que fazer
            expected_output: "Roteiro completo pronto para produção." # O que se espera ao final
            # agent: roteirista # Opcional se a tarefa está sob o 'role' que a executa
                               # Mas útil se um 'manager_agent' distribui tarefas.
            # context: # Opcional: especificaria quais tarefas devem ser concluídas antes desta
            #   - tarefa_ideias_brainstorm
    ```
    > No exemplo acima, `tarefa_escrita_roteiro` é uma tarefa atribuída implicitamente ao agente `roteirista`.
    > Em cenários mais complexos, você pode ter uma lista global de tarefas e atribuí-las explicitamente aos agentes.
    > Consulte os arquivos YAML em `examples/cookbooks/yaml/` para ver diversas formas de estruturar tarefas. Por exemplo, em `examples/cookbooks/yaml/comprehensive_research_report_agents.ipynb` (que usa um YAML), você verá tarefas mais elaboradas.

### Fluxo de Execução de Tarefas

1.  **Atribuição:** Uma tarefa é atribuída a um agente.
2.  **Execução:** O agente usa suas instruções, LLM e ferramentas para trabalhar na tarefa.
3.  **Resultado:** O agente produz um resultado.
4.  **Avaliação (implícita ou explícita):** O resultado é comparado (pelo agente, por outro agente ou pelo sistema) com o `expected_output`.
5.  **Passagem de Contexto:** O resultado da tarefa pode se tornar contexto para tarefas subsequentes.

### A Importância do "Expected Output"

O campo `expected_output` é vital. Ele serve como:
*   Um guia para o LLM do agente, ajudando-o a entender o formato e o escopo do que precisa ser produzido.
*   Um critério para a auto-reflexão do agente ou para agentes avaliadores determinarem se a tarefa foi bem-sucedida.
*   Uma forma de garantir que a saída de uma tarefa seja utilizável pela próxima tarefa em um workflow.

## Fundamentos por Trás

O conceito de tarefas está ligado a:

*   **Decomposição de Problemas:** Dividir um problema complexo em partes menores e gerenciáveis (as tarefas).
*   **Planejamento:** Em sistemas mais avançados, os próprios agentes podem gerar uma sequência de tarefas para atingir um objetivo maior.
*   **Gerenciamento de Workflow:** Orquestrar a ordem de execução das tarefas, lidar com dependências e paralelismo.

Ao definir tarefas claras e com resultados esperados bem descritos, você aumenta significativamente a chance de seus agentes PraisonAI alcançarem os objetivos desejados de forma eficaz.

A seguir, exploraremos como os **Processos** gerenciam a execução e colaboração entre agentes e suas tarefas.
